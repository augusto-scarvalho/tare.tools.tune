// The natural voice's spec layer (concat.render_spoken and concat.frames).
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <new>
#include <vector>

#include "rng.hpp"
#include "tare_tune.h"
#include "vocoder.hpp"

struct tt_bank {
    int32_t bands = 0;
    std::vector<double> f0;    // Hz
    std::vector<uint8_t> env;  // frames x bands, 0.5 dB steps above ENV_FLOOR
    std::vector<float> ap;     // frames x 5: float32 / 255, as the Python bank keeps it
    std::size_t frames() const { return f0.size(); }
};

namespace tune {
namespace {

inline constexpr int SMOOTH = 3;   // frames cross-faded on each side of a join

// concat.frames: the bank's frames along the pieces; joins cross-fade both pieces, each carried on past its cut
void frames(const tt_bank &b, const double *pieces, int32_t n_pieces, const int32_t *joins, int32_t n_joins,
            Clip &clip, std::vector<bool> &voiced) {
    const int B = b.bands;
    std::vector<double> src, rate;
    std::vector<std::size_t> starts{0};
    for (int32_t p = 0; p < n_pieces; ++p) {
        const double s = pieces[3 * p], e = pieces[3 * p + 1];
        const auto n = static_cast<std::size_t>(pieces[3 * p + 2]);
        for (std::size_t i = 0; i < n; ++i) src.push_back(s + (static_cast<double>(i) + 0.5) / n * (e - s));
        rate.insert(rate.end(), n, (e - s) / n);
        starts.push_back(starts.back() + n);
    }
    const std::size_t N = src.size();
    const long long last = static_cast<long long>(b.frames()) - 1;
    clip.bands = B;
    clip.env.assign(N * B, 0.0);
    clip.ap.assign(N * AP_BANDS, 0.0);
    voiced.assign(N, false);

    auto at = [&](double x, double *env, double *ap, bool &v) {
        const long long lo = std::clamp(static_cast<long long>(std::floor(x)), 0LL, last);
        const long long hi = std::min(lo + 1, last);
        const double w = std::clamp(x - static_cast<double>(lo), 0.0, 1.0);
        for (int k = 0; k < B; ++k) {
            const double a = b.env[lo * B + k] / 2.0 + ENV_FLOOR, c = b.env[hi * B + k] / 2.0 + ENV_FLOOR;
            env[k] = a * (1 - w) + c * w;
        }
        for (int k = 0; k < AP_BANDS; ++k)
            ap[k] = static_cast<double>(b.ap[lo * AP_BANDS + k]) * (1 - w) +
                    static_cast<double>(b.ap[hi * AP_BANDS + k]) * w;
        v = b.f0[std::clamp(static_cast<long long>(std::nearbyint(x)), 0LL, last)] > 0;   // np.round: half to even
    };
    for (std::size_t i = 0; i < N; ++i) {
        bool v;
        at(src[i], &clip.env[i * B], &clip.ap[i * AP_BANDS], v);
        voiced[i] = v;
    }
    std::vector<double> ea(B), eb(B), aa(AP_BANDS), ab(AP_BANDS);
    for (int32_t q = 0; q < n_joins; ++q) {
        const long long j = static_cast<long long>(starts[joins[q]]);
        const long long o0 = std::max(j - SMOOTH, 1LL), o1 = std::min(j + SMOOTH, static_cast<long long>(N) - 1);
        if (o1 <= o0) continue;
        const double len = static_cast<double>(o1 - o0);
        for (long long o = o0; o < o1; ++o) {
            bool va, vb;
            at(src[j - 1] + static_cast<double>(o - (j - 1)) * rate[j - 1], ea.data(), aa.data(), va);
            at(src[j] + static_cast<double>(o - j) * rate[j], eb.data(), ab.data(), vb);
            const double w = (static_cast<double>(o - o0) + 0.5) / len;
            for (int k = 0; k < B; ++k) clip.env[o * B + k] = ea[k] * (1 - w) + eb[k] * w;
            for (int k = 0; k < AP_BANDS; ++k) clip.ap[o * AP_BANDS + k] = aa[k] * (1 - w) + ab[k] * w;
            voiced[o] = w < 0.5 ? va : vb;
        }
    }
}

// np.linspace(0, n - 1, m)
std::vector<double> linspace_to(std::size_t n, std::size_t m) {
    std::vector<double> x(m, 0.0);
    if (m < 2) return x;
    const double step = static_cast<double>(n - 1) / static_cast<double>(m - 1);
    for (std::size_t i = 0; i < m; ++i) x[i] = static_cast<double>(i) * step;
    x[m - 1] = static_cast<double>(n - 1);
    return x;
}

double peak_of(const std::vector<double> &x) {
    double p = 0.0;
    for (double v : x) p = std::max(p, std::abs(v));
    return p;
}

}  // namespace
}  // namespace tune

using namespace tune;

extern "C" {

tt_bank *tt_bank_new(int32_t n, int32_t bands, const float *f0, const uint8_t *env, const uint8_t *ap) {
    if (n <= 0 || (bands != 32 && bands != 64) || !f0 || !env || !ap) return nullptr;
    auto *b = new (std::nothrow) tt_bank;
    if (!b) return nullptr;
    b->bands = bands;
    b->f0.assign(f0, f0 + n);
    b->env.assign(env, env + static_cast<std::size_t>(n) * bands);
    b->ap.resize(static_cast<std::size_t>(n) * AP_BANDS);
    for (std::size_t i = 0; i < b->ap.size(); ++i) b->ap[i] = static_cast<float>(ap[i]) / 255.0f;
    return b;
}

void tt_bank_free(tt_bank *bank) { delete bank; }

uint64_t tt_key(uint64_t seed, const char *label, int64_t index) {
    return index < 0 ? key(seed, label) : key(seed, label, static_cast<uint64_t>(index));
}

int32_t tt_render_spoken(const tt_bank *bank, const double *pieces, int32_t n_pieces, const int32_t *joins,
                         int32_t n_joins, const double *f0, int32_t n_f0, double warp, double breath, double tilt,
                         double rough, double sub, double gain, uint64_t seed, int32_t sr, double **out,
                         int32_t *n_out) {
    if (!bank || !pieces || n_pieces <= 0 || !f0 || n_f0 <= 0 || !out || !n_out || sr <= 0) return 1;
    for (int32_t q = 0; q < n_joins; ++q)
        if (joins[q] <= 0 || joins[q] > n_pieces) return 1;
    try {
        Clip clip;
        std::vector<bool> voiced;
        frames(*bank, pieces, n_pieces, joins, n_joins, clip, voiced);
        const std::size_t N = voiced.size();
        const std::vector<double> xp = linspace_to(N, static_cast<std::size_t>(n_f0));
        clip.f0.resize(N);
        for (std::size_t i = 0; i < N; ++i)
            clip.f0[i] = voiced[i] ? interp(static_cast<double>(i), xp.data(), f0, static_cast<std::size_t>(n_f0)) : 0.0;
        std::vector<double> y = synthesize(clip, sr, 1.0, warp, 1.0, breath, tilt, 1.0, key(seed, "spoken"), rough,
                                           sub);
        const double peak = peak_of(y) + 1e-12;
        auto *buf = static_cast<double *>(std::malloc(y.size() * sizeof(double)));
        if (!buf) return 2;
        for (std::size_t i = 0; i < y.size(); ++i) buf[i] = gain * y[i] / peak;
        *out = buf;
        *n_out = static_cast<int32_t>(y.size());
        return 0;
    } catch (...) {
        return 3;
    }
}

void tt_free(void *buffer) { std::free(buffer); }

}  // extern "C"
