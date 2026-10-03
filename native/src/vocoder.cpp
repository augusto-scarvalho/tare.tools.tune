// A line-by-line port of vocoder.synthesize; the comments name the Python it follows.
#include "vocoder.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <stdexcept>

#include "pocketfft_hdronly.h"
#include "rng.hpp"
#include "tables.hpp"

namespace tune {

using cd = std::complex<double>;
static constexpr double PI = 3.141592653589793;

double interp(double x, const double *xp, const double *fp, std::size_t m) {
    // numpy's arr_interp: left/right values outside, the exact point on a knot, else the slope from the left knot
    if (std::isnan(x)) return x;
    if (x < xp[0]) return fp[0];
    if (x > xp[m - 1]) return fp[m - 1];
    std::size_t j = static_cast<std::size_t>(std::upper_bound(xp, xp + m, x) - xp) - 1;   // xp[j] <= x < xp[j + 1]
    if (j >= m - 1 || xp[j] == x) return fp[j];
    const double slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    double y = slope * (x - xp[j]) + fp[j];
    if (std::isnan(y)) {
        y = slope * (x - xp[j + 1]) + fp[j + 1];
        if (std::isnan(y) && fp[j] == fp[j + 1]) y = fp[j];
    }
    return y;
}

namespace {

constexpr std::ptrdiff_t REAL = sizeof(double), COMPLEX = sizeof(cd);   // pocketfft strides, in bytes

// np.fft.rfft(x, nfft): x cropped or zero-padded to nfft
void rfft(const double *x, std::size_t n, std::size_t nfft, std::vector<double> &buf, std::vector<cd> &out) {
    buf.assign(nfft, 0.0);
    std::copy(x, x + std::min(n, nfft), buf.begin());
    out.resize(nfft / 2 + 1);
    pocketfft::r2c<double>({nfft}, {REAL}, {COMPLEX}, 0, pocketfft::FORWARD, buf.data(), out.data(), 1.0);
}

// np.fft.irfft(X, nfft)
void irfft(const cd *x, std::size_t nfft, std::vector<double> &out) {
    out.resize(nfft);
    pocketfft::c2r<double>({nfft}, {COMPLEX}, {REAL}, 0, pocketfft::BACKWARD, x, out.data(),
                           1.0 / static_cast<double>(nfft));
}

// _min_phase: a minimum-phase spectrum of the given magnitude (folded real cepstrum)
void min_phase(const std::vector<double> &mag, std::size_t nfft, std::vector<cd> &out) {
    std::vector<cd> lg(mag.size());
    for (std::size_t k = 0; k < mag.size(); ++k) lg[k] = cd(std::log(std::max(mag[k], 1e-12)), 0.0);
    std::vector<double> c, buf;
    irfft(lg.data(), nfft, c);
    for (std::size_t i = 1; i < nfft / 2; ++i) c[i] *= 2;
    for (std::size_t i = nfft / 2 + 1; i < nfft; ++i) c[i] = 0;
    rfft(c.data(), nfft, nfft, buf, out);
    for (auto &z : out) z = std::exp(z);
}

}  // namespace

std::vector<double> synthesize(const Clip &t, int sr, double pitch, double warp, double stretch, double breath,
                               double tilt, double swing, uint64_t seed) {
    const std::size_t len = t.frames();
    const int B = t.bands;
    const double *bf = B == 64 ? BAND_FREQS_64 : B == 32 ? BAND_FREQS_32 : nullptr;
    if (!bf || len == 0) throw std::invalid_argument("the vocoder takes 32 or 64 envelope bands and some frames");

    // n_frames = max(int(round(len(t.f0) * stretch)), 2); then the clip, read at its new pace
    const std::size_t n_frames = std::max<std::size_t>(
        static_cast<std::size_t>(std::nearbyint(static_cast<double>(len) * stretch)), 2);
    std::vector<double> env(n_frames * B), ap(n_frames * AP_BANDS), f0(n_frames), performed(n_frames);
    for (std::size_t i = 0; i < n_frames; ++i) {
        const double src = std::min(static_cast<double>(i) / stretch, static_cast<double>(len - 1));
        const std::size_t lo = static_cast<std::size_t>(std::floor(src)), hi = std::min(lo + 1, len - 1);
        const double w = src - static_cast<double>(lo);
        for (int b = 0; b < B; ++b) env[i * B + b] = t.env[lo * B + b] * (1 - w) + t.env[hi * B + b] * w;
        for (int b = 0; b < AP_BANDS; ++b)
            ap[i * AP_BANDS + b] = t.ap[lo * AP_BANDS + b] * (1 - w) + t.ap[hi * AP_BANDS + b] * w;
        f0[i] = (t.f0[lo] > 0 && t.f0[hi] > 0) ? t.f0[lo] * (1 - w) + t.f0[hi] * w : t.f0[lo];
    }
    performed = f0;
    if (swing != 1.0 && t.pitch > 0)
        for (auto &f : f0) f = f > 0 ? t.pitch * std::pow(std::max(f, 1.0) / t.pitch, swing) : 0.0;
    for (auto &f : f0) f = f * pitch;
    for (auto &a : ap) a = breath >= 0 ? a + breath * (1 - a) : a * (1 + breath);

    const std::size_t nfft = sr > 32000 ? 2048 : 1024, nb = nfft / 2 + 1;
    const double *dc = nfft == 2048 ? DC_2048 : DC_1024;
    std::vector<double> freqs(nb), src_f(nb), log_src_f(nb), slope(nb);
    const double val = 1.0 / (static_cast<double>(nfft) * (1.0 / sr));            // np.fft.rfftfreq(nfft, 1 / sr)
    for (std::size_t k = 0; k < nb; ++k) {
        freqs[k] = static_cast<double>(k) * val;
        src_f[k] = std::max(freqs[k] / warp, 1.0);
        log_src_f[k] = std::log(src_f[k]);
        slope[k] = tilt * std::log2(std::max(freqs[k], 50.0) / 1000);
    }

    // filters(k): the voice and the breath responses of frame k
    std::vector<cd> voice, air;
    bool voiced = false;
    std::vector<double> db(nb), power(nb), mag(nb);
    auto filters = [&](std::size_t k) {
        const double *e = &env[k * B];
        const double f_low = performed[k] > 0 ? performed[k] : UNVOICED;
        const double held = interp(f_low, bf, e, B);
        for (std::size_t q = 0; q < nb; ++q) {
            db[q] = src_f[q] < f_low ? held : interp(src_f[q], bf, e, B);
            power[q] = std::pow(10.0, ((db[q] + slope[q]) - 3 * std::log2(std::max(f_low / src_f[q], 1.0))) / 10);
        }
        voiced = f0[k] > 0;
        if (!voiced) {
            for (std::size_t q = 0; q < nb; ++q) mag[q] = std::sqrt(power[q]);
            min_phase(mag, nfft, air);
            return;
        }
        std::vector<double> a(nb);
        for (std::size_t q = 0; q < nb; ++q)
            a[q] = std::clamp(interp(log_src_f[q], LOG_AP_FREQS, &ap[k * AP_BANDS], AP_BANDS), 0.0, 1.0);
        for (std::size_t q = 0; q < nb; ++q) mag[q] = std::sqrt(power[q] * (1 - a[q]));
        min_phase(mag, nfft, voice);
        for (std::size_t q = 0; q < nb; ++q) mag[q] = std::sqrt(power[q] * a[q]);
        min_phase(mag, nfft, air);
    };

    std::vector<double> out(static_cast<std::size_t>(static_cast<double>(n_frames) * FRAME * sr) + 2 * nfft, 0.0);
    std::vector<double> noise_buf, buf, y, h;
    std::vector<cd> spec;
    const uint64_t breath_key = key(seed, "breath");
    double when = 0.0;
    std::size_t i = 0, cached = SIZE_MAX;
    while (true) {                          // one pulse per glottal period (every 2 ms where there is no voice)
        const std::size_t k = static_cast<std::size_t>(when / FRAME + 1e-9);
        if (k >= n_frames) break;
        const double f = f0[k] > 0 ? f0[k] : UNVOICED;
        const double pos = when * sr;
        const std::size_t s = static_cast<std::size_t>(pos);
        const std::size_t n = static_cast<std::size_t>(
            std::max<long long>(static_cast<long long>((when + 1 / f) * sr) - static_cast<long long>(s), 1));
        if (k != cached) {
            filters(k);
            cached = k;
        }
        noise(key(breath_key, static_cast<uint64_t>(i)), n, noise_buf);      // breath: noise to the next pulse
        double mean = 0.0;
        for (double v : noise_buf) mean += v;
        mean /= static_cast<double>(n);
        for (double &v : noise_buf) v -= mean;
        rfft(noise_buf.data(), n, nfft, buf, spec);
        for (std::size_t q = 0; q < nb; ++q) spec[q] *= air[q];
        irfft(spec.data(), nfft, y);
        for (double &v : y) v *= BREATH;
        if (voiced) {                        // voice: a minimum-phase pulse, between samples, without DC
            const double frac = pos - static_cast<double>(s), inv_sr = 1.0 / sr;
            for (std::size_t q = 0; q < nb; ++q) {      // numpy divides a complex array by sr as x * (1 / sr)
                const double theta = ((-2.0 * PI) * freqs[q] * inv_sr) * frac;
                spec[q] = voice[q] * cd(std::cos(theta), std::sin(theta));
            }
            irfft(spec.data(), nfft, h);
            double sum = 0.0;
            for (double v : h) sum += v;
            for (std::size_t q = 0; q < nfft / 2; ++q) h[q] -= sum * dc[q];
            const double gain = std::sqrt(static_cast<double>(n));
            for (std::size_t q = 0; q < nfft; ++q) y[q] += h[q] * gain;
        }
        for (std::size_t q = 0; q < nfft && s + q < out.size(); ++q) out[s + q] += y[q];
        when += 1 / f;
        ++i;
    }
    double peak = 0.0;                      // trim the silent tail
    for (double v : out) peak = std::max(peak, std::abs(v));
    const double floor = 1e-4 * (peak + 1e-12);
    std::size_t end = out.size();
    while (end > 0 && std::abs(out[end - 1]) <= floor) --end;
    out.resize(end ? end : static_cast<std::size_t>(FRAME * sr));
    return out;
}

}  // namespace tune
