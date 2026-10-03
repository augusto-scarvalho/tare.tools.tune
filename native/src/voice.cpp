// A whole voice spec (render.render): syllables, struck bodies, noise bands, scattered events and natural speech,
// then the finishing chain. A line-by-line port of src/tare/tools/tune/render.py and layers.py; the comments name
// the Python each piece follows. scipy's filters are rebuilt here from the same formulas (butter -> bilinear zpk).
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdlib>
#include <cstring>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "json.hpp"
#include "pocketfft_hdronly.h"
#include "rng.hpp"
#include "tare_tune.h"
#include "vocoder.hpp"

namespace tune {
namespace {

constexpr double PI = 3.141592653589793;
constexpr std::size_t BLOCK = 64;   // filter coefficient update interval, samples
constexpr double PEAK = 0.89;       // -1 dBFS

using Vec = std::vector<double>;
using Rows = std::vector<Vec>;      // curves (time, value) and lists of tuples, as JSON arrays of arrays
using cd = std::complex<double>;

struct Unsupported : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// -- numpy ---------------------------------------------------------------------------------------------------------

Vec linspace(double a, double b, std::size_t n) {
    Vec y(n);
    if (n == 1) y[0] = a;
    if (n < 2) return y;
    const double step = (b - a) / static_cast<double>(n - 1);
    for (std::size_t i = 0; i < n; ++i) y[i] = static_cast<double>(i) * step + a;
    y[n - 1] = b;
    return y;
}

double peak(const Vec &x) {
    double p = 0.0;
    for (double v : x) p = std::max(p, std::abs(v));
    return p;
}

double pymod1(double a) {   // a % 1.0
    double m = std::fmod(a, 1.0);
    if (m != 0 && m < 0) m += 1.0;
    return m == 0 ? 0.0 : m;
}

// render.curve: breakpoints over n samples, optionally in log space
Vec curve(const Rows &points, std::size_t n, bool log = false) {
    if (points.empty()) throw std::runtime_error("a curve needs at least one point");
    Vec xs, ys;
    for (const Vec &p : points) {
        xs.push_back(p.at(0));
        ys.push_back(log ? std::log(std::max(p.at(1), 1e-9)) : p.at(1));
    }
    const Vec t = linspace(0.0, 1.0, n);
    Vec out(n);
    for (std::size_t i = 0; i < n; ++i) {
        out[i] = interp(t[i], xs.data(), ys.data(), xs.size());
        if (log) out[i] = std::exp(out[i]);
    }
    return out;
}

// render.smooth_noise: random wander in [-1, 1] with about `rate` control points per second
Vec smooth_noise(uint64_t k, std::size_t n, int sr, double rate) {
    const auto points =
        static_cast<std::size_t>(std::max<long long>(2, static_cast<long long>(static_cast<double>(n) / sr * rate) + 2));
    const Vec x = linspace(0.0, static_cast<double>(points - 1), n), v = noise(k, points);
    Vec xp(points), out(n);
    for (std::size_t i = 0; i < points; ++i) xp[i] = static_cast<double>(i);
    for (std::size_t i = 0; i < n; ++i) out[i] = interp(x[i], xp.data(), v.data(), points);
    return out;
}

// -- scipy.signal --------------------------------------------------------------------------------------------------

struct Ba {
    Vec b, a;
};

// lfilter: transposed direct form II, with scipy's order of operations
Vec lfilter(Vec b, Vec a, const Vec &x, Vec z = {}) {
    const std::size_t K = std::max(b.size(), a.size());
    b.resize(K, 0.0);
    a.resize(K, 0.0);
    const double a0 = a[0];
    for (double &v : b) v /= a0;
    for (double &v : a) v /= a0;
    z.resize(K - 1, 0.0);
    Vec y(x.size());
    for (std::size_t i = 0; i < x.size(); ++i) {
        const double xn = x[i];
        if (K == 1) {
            y[i] = xn * b[0];
            continue;
        }
        const double yn = z[0] + b[0] * xn;
        for (std::size_t j = 0; j + 2 < K; ++j) z[j] = z[j + 1] + xn * b[j + 1] - yn * a[j + 1];
        z[K - 2] = xn * b[K - 1] - yn * a[K - 1];
        y[i] = yn;
    }
    return y;
}

// sosfilt over one second-order section (scipy's _sosfilt), in place
void sosfilt(const Ba &f, Vec &x) {
    Vec b = f.b, a = f.a;
    b.resize(3, 0.0);
    a.resize(3, 0.0);
    double z0 = 0, z1 = 0;
    for (double &v : x) {
        const double y = b[0] * v + z0;
        z0 = b[1] * v - a[1] * y + z1;
        z1 = b[2] * v - a[2] * y;
        v = y;
    }
}

// np.poly: the polynomial with these roots, real when they come in conjugate pairs
Vec poly(const std::vector<cd> &roots) {
    std::vector<cd> c{1.0};
    for (const cd &r : roots) {
        std::vector<cd> next(c.size() + 1, 0.0);
        for (std::size_t i = 0; i < c.size(); ++i) {
            next[i] += c[i];
            next[i + 1] += c[i] * -r;
        }
        c = std::move(next);
    }
    Vec out;
    for (const cd &v : c) out.push_back(v.real());
    return out;
}

// butter(N, Wn, btype): Butterworth prototype -> lp2lp/lp2hp/lp2bp -> bilinear, as (b, a); Wn is relative to Nyquist.
// An order-1 or order-2 filter is also its own single second-order section (output="sos").
Ba butter(int N, double lo, double hi, char type) {
    std::vector<cd> p;
    for (int m = -N + 1; m < N; m += 2) p.push_back(-std::exp(cd(0.0, PI * m / (2.0 * N))));
    std::vector<cd> z;
    double k = 1.0;
    const auto warp = [](double wn) { return 2 * 2.0 * std::tan(PI * wn / 2.0); };
    const double w0 = warp(lo);
    const std::size_t degree = p.size() - z.size();
    if (type == 'l') {
        for (cd &v : p) v *= w0;
        k *= std::pow(w0, static_cast<double>(degree));
    } else if (type == 'h') {
        cd prod = 1.0;
        for (const cd &v : p) prod *= -v;
        for (cd &v : p) v = w0 / v;
        z.assign(degree, 0.0);
        k *= (1.0 / prod).real();
    } else {   // band
        const double w1 = warp(hi), bw = w1 - w0, wo = std::sqrt(w0 * w1);
        std::vector<cd> plus, minus;
        for (const cd &v : p) {
            const cd lp = v * bw / 2.0, root = std::sqrt(lp * lp - wo * wo);
            plus.push_back(lp + root);
            minus.push_back(lp - root);
        }
        p = plus;
        p.insert(p.end(), minus.begin(), minus.end());
        z.assign(degree, 0.0);
        k *= std::pow(bw, static_cast<double>(degree));
    }
    const double fs2 = 4.0;   // bilinear_zpk at fs = 2
    cd num = 1.0, den = 1.0;
    for (const cd &v : z) num *= fs2 - v;
    for (const cd &v : p) den *= fs2 - v;
    std::vector<cd> zz, pz;
    for (const cd &v : z) zz.push_back((fs2 + v) / (fs2 - v));
    for (const cd &v : p) pz.push_back((fs2 + v) / (fs2 - v));
    zz.resize(pz.size(), -1.0);
    k *= (num / den).real();
    Ba f{poly(zz), poly(pz)};
    for (double &v : f.b) v *= k;
    return f;
}

// -- render.py -----------------------------------------------------------------------------------------------------

// render.time_varying: a biquad whose coefficients change every BLOCK samples, its history carried across
Vec time_varying(const Vec &x, const std::vector<Ba> &coeffs) {
    Vec y(x.size());
    double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (std::size_t i = 0; i < coeffs.size(); ++i) {
        const std::size_t k = i * BLOCK;
        if (k >= x.size()) break;
        const Vec seg(x.begin() + k, x.begin() + std::min(k + BLOCK, x.size()));
        const Vec &b = coeffs[i].b, &a = coeffs[i].a;
        const Vec zi{b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2, b[2] * x1 - a[2] * y1};
        const Vec out = lfilter(b, a, seg, zi);
        std::copy(out.begin(), out.end(), y.begin() + k);
        if (seg.size() >= 2) {
            x1 = seg[seg.size() - 1], x2 = seg[seg.size() - 2], y1 = out[out.size() - 1], y2 = out[out.size() - 2];
        } else {
            x2 = x1, y2 = y1, x1 = seg.back(), y1 = out.back();
        }
    }
    return y;
}

// render.bandpass_coeffs: RBJ band-pass with 0 dB peak gain
Ba bandpass(double f, double bw, int sr) {
    f = std::min(f, 0.45 * sr);
    const double w0 = 2 * PI * f / sr, alpha = std::sin(w0) * std::min(bw, f) / (2 * f), a0 = 1 + alpha;
    return {{alpha / a0, 0.0, -alpha / a0}, {1.0, -2 * std::cos(w0) / a0, (1 - alpha) / a0}};
}

Vec envelope(const Rows &amp, double attack, double release, std::size_t n, int sr) {
    Vec env = curve(amp, n);
    const auto a = static_cast<std::size_t>(std::min<long long>(std::max<long long>(static_cast<long long>(attack * sr), 1), n));
    const auto r = static_cast<std::size_t>(std::min<long long>(std::max<long long>(static_cast<long long>(release * sr), 1), n));
    const Vec up = linspace(0.0, 1.0, a), down = linspace(1.0, 0.0, r);
    for (std::size_t i = 0; i < a; ++i) env[i] *= up[i] * up[i];
    for (std::size_t i = 0; i < r; ++i) env[n - r + i] *= down[i] * down[i];
    return env;
}

std::size_t samples(double seconds, int sr) {   // max(int(seconds * sr), 16)
    return static_cast<std::size_t>(std::max<long long>(static_cast<long long>(seconds * sr), 16));
}

Vec normalised(Vec x, double gain) {   // gain * x / (np.max(np.abs(x)) + 1e-12)
    const double p = peak(x) + 1e-12;
    for (double &v : x) v = gain * v / p;
    return x;
}

double polyblep(double t, double dt) {
    double out = 0.0;
    if (t < dt) {
        const double x = t / dt;
        out = 2 * x - x * x - 1;
    }
    if (t > 1 - dt) {
        const double x = (t - 1) / dt;
        out = x * x + 2 * x + 1;
    }
    return out;
}

struct Spec {   // one layer's fields, with the dataclass defaults of spec.py
    const Json &j;
    double num(const char *key, double fallback) const { return j.number(key, fallback); }
    Vec tuple(const char *key, Vec fallback) const {   // a fixed-size tuple, or (empty fallback) a list
        const Json *v = j.get(key);
        if (!v || v->kind != Json::ARR) return fallback;
        Vec out;
        for (const Json &e : v->arr) out.push_back(e.num);
        if (!fallback.empty() && out.size() != fallback.size())
            throw std::runtime_error(std::string("'") + key + "' needs " + std::to_string(fallback.size()) + " numbers");
        return out;
    }
    Rows rows(const char *key, Rows fallback, std::size_t width) const {   // a list of tuples (curves: 2 wide)
        const Json *v = j.get(key);
        if (!v || v->kind != Json::ARR) return fallback;
        Rows out;
        for (const Json &e : v->arr) {
            Vec row;
            for (const Json &c : e.arr) row.push_back(c.num);
            if (row.size() < width)
                throw std::runtime_error(std::string("each of '") + key + "' needs " + std::to_string(width) + " numbers");
            out.push_back(std::move(row));
        }
        return out;
    }
};

const Rows FLAT{{0.0, 1.0}, {1.0, 1.0}};

// render.render_syllable: source -> formants -> envelope
Vec syllable(const Spec &s, int sr, uint64_t k) {
    const std::size_t n = samples(s.num("dur", 0), sr);
    const std::string source = s.j.text("source", "glottal");
    Vec f0 = curve(s.rows("pitch", {}, 2), n, true);
    const Vec vibrato = s.tuple("vibrato", {0, 0});
    const double jitter = s.num("jitter", 0);
    const Vec wander = jitter ? smooth_noise(key(k, "jitter"), n, sr, 25) : Vec(n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sr;
        const double w = jitter ? jitter * wander[i] : 0.0;
        f0[i] = std::clamp(f0[i] * std::pow(2.0, (vibrato[1] * std::sin(2 * PI * vibrato[0] * t) + w) / 12), 1.0,
                           0.49 * sr);
    }
    // _source
    Vec cycles(n), x(n);
    double sum = 0.0;
    for (std::size_t i = 0; i < n; ++i) cycles[i] = sum += f0[i] / sr;
    if (source == "noise") {
        x = noise(key(k, "source"), n);
        for (double &v : x) v *= 0.8;
    } else {
        const double width = s.num("pulse_width", 0.5);
        for (std::size_t i = 0; i < n; ++i) {
            const double t = pymod1(cycles[i]), dt = std::min(f0[i] / sr, 0.5);
            if (source == "sine")
                x[i] = std::sin(2 * PI * cycles[i]) + 0.12 * std::sin(4 * PI * cycles[i]);
            else if (source == "pulse")
                x[i] = (t < width ? 1.0 : -1.0) + polyblep(t, dt) - polyblep(pymod1(t - width), dt);
            else if (source == "glottal")
                x[i] = 2 * t - 1 - polyblep(t, dt);
            else
                throw std::runtime_error("unknown source " + source);
        }
    }
    if (source == "glottal" || source == "pulse") {
        Vec sorted = f0;
        std::sort(sorted.begin(), sorted.end());
        const double median = n % 2 ? sorted[n / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
        const double brightness = s.num("brightness", 0.5);
        const double fc = std::min(median * (1.5 + 40 * brightness * brightness), 0.45 * sr);
        const Ba f = butter(1, fc / (sr / 2.0), 0, 'l');
        x = lfilter(f.b, f.a, x);
    }
    if (const double sub = s.num("sub", 0))
        for (std::size_t i = 0; i < n; ++i) x[i] = x[i] * (1 + sub * std::cos(PI * cycles[i]));
    if (const double breath = s.num("breath", 0)) {
        const Vec air = noise(key(k, "breath"), n);
        for (std::size_t i = 0; i < n; ++i) x[i] = x[i] * (1 - breath) + breath * air[i] * 0.7;
    }
    const Vec ring = s.tuple("ring", {0, 0});
    if (ring[1])
        for (std::size_t i = 0; i < n; ++i)
            x[i] = x[i] * (1 - ring[1] + ring[1] * std::sin(2 * PI * ring[0] * static_cast<double>(i) / sr));
    // _formants
    const Rows formants = s.rows("formants", {}, 3), mouth = s.rows("mouth", FLAT, 2);
    if (!formants.empty()) {
        Vec out(n, 0.0);
        std::set<double> shapes;
        for (const Vec &m : mouth) shapes.insert(m.at(1));
        const std::size_t blocks = (n + BLOCK - 1) / BLOCK;
        const Vec scale = shapes.size() == 1 ? Vec{} : curve(mouth, blocks, true);
        for (const Vec &f : formants) {
            Vec y;
            if (shapes.size() == 1) {   // a still mouth (an instrument's body): one fixed filter per formant
                const double m = mouth[0][1];
                const Ba c = bandpass(f[0] * m, f[1] * m, sr);
                y = lfilter(c.b, c.a, x);
            } else {
                std::vector<Ba> coeffs;
                for (double m : scale) coeffs.push_back(bandpass(f[0] * m, f[1] * m, sr));
                y = time_varying(x, coeffs);
            }
            for (std::size_t i = 0; i < n; ++i) out[i] += f[2] * y[i];
        }
        x = std::move(out);
    }
    // envelope
    Vec env = envelope(s.rows("amp", FLAT, 2), s.num("attack", 0.01), s.num("release", 0.05), n, sr);
    const Vec rough = s.tuple("rough", {0, 30});
    if (rough[0]) {
        const Vec sn = smooth_noise(key(k, "rough"), n, sr, 8);
        for (std::size_t i = 0; i < n; ++i)
            env[i] *= 1 - rough[0] * (0.5 + 0.5 * std::sin(2 * PI * rough[1] * (static_cast<double>(i) / sr) + 3 * sn[i]));
    }
    if (const double shimmer = s.num("shimmer", 0)) {
        const Vec sn = smooth_noise(key(k, "shimmer"), n, sr, 60);
        for (std::size_t i = 0; i < n; ++i) env[i] *= std::max(1 + shimmer * sn[i], 0.0);
    }
    const Vec pulses = s.tuple("pulses", {0, 0, 2});
    if (pulses[1])
        for (std::size_t i = 0; i < n; ++i)
            env[i] *= 1 - pulses[1] +
                      pulses[1] * std::pow(0.5 - 0.5 * std::cos(2 * PI * pulses[0] * (static_cast<double>(i) / sr)), pulses[2]);
    for (std::size_t i = 0; i < n; ++i) x[i] = x[i] * env[i];
    return normalised(std::move(x), s.num("gain", 1));
}

// -- layers.py -----------------------------------------------------------------------------------------------------

// layers.render_modal: an excitation rings a bank of decaying resonators
Vec modal(const Spec &m, int sr, uint64_t k) {
    const std::size_t n = samples(m.num("dur", 0), sr);
    Vec exc(n, 0.0);
    const Rows hits = m.rows("hits", {{0.0, 1.0, 0.001}}, 3);
    for (std::size_t i = 0; i < hits.size(); ++i) {
        const auto a = static_cast<std::size_t>(hits[i][0] * sr), L = static_cast<std::size_t>(hits[i][2] * sr);
        const double gain = hits[i][1];
        if (a >= n) continue;
        if (L < 3) {   // an ideal strike: a unit impulse, every mode excited at its own gain
            exc[a] += gain;
            continue;
        }
        const Vec burst = noise(key(k, "hit", static_cast<uint64_t>(i)), L);
        for (std::size_t j = 0; j < L && a + j < n; ++j) {
            const double hann = 0.5 + 0.5 * std::cos(PI * (1.0 - static_cast<double>(L) + 2.0 * j) / static_cast<double>(L - 1));
            exc[a + j] += burst[j] * hann * gain;
        }
    }
    const Vec scrape = m.tuple("scrape", {0, 0, 0, 0});
    if (scrape[2] && scrape[1]) {
        const auto a = static_cast<std::size_t>(scrape[0] * sr);
        const auto L = static_cast<std::size_t>(std::max<long long>(static_cast<long long>(scrape[1] * sr), 2));
        const Vec s = noise(key(k, "scrape"), L);
        for (std::size_t j = 0; j < L && a + j < n; ++j) {
            const double sine = std::sin(PI * static_cast<double>(j) / static_cast<double>(L));
            double v = s[j] * (sine * sine) * scrape[2] * 0.3;
            if (scrape[3]) v *= 1 + 0.8 * std::sin(2 * PI * scrape[3] * (static_cast<double>(j) / sr));   // stick-slip
            exc[a + j] += v;
        }
    }
    const Ba hard = butter(1, std::min(m.num("hardness", 8000), 0.45 * sr) / (sr / 2.0), 0, 'l');
    exc = lfilter(hard.b, hard.a, exc);
    const double click = m.num("click", 0);
    Vec out(n);
    for (std::size_t i = 0; i < n; ++i) out[i] = click * exc[i];
    for (const Vec &mode : m.rows("modes", {}, 3)) {
        const double hz = mode[0], t60 = mode[1], gain = mode[2];
        if (!(20 <= hz && hz < 0.45 * sr)) continue;
        const double r = std::pow(10.0, -3 / (std::max(t60, 1e-4) * sr)), w = 2 * PI * hz / sr;   // layers.resonator
        const Vec y = lfilter({std::sin(w)}, {1.0, -2 * r * std::cos(w), r * r}, exc);
        for (std::size_t i = 0; i < n; ++i) out[i] = out[i] + gain * y[i];
    }
    const double damp = m.num("damp", 0);
    if (0 < damp && damp < m.num("dur", 0)) {   // damped: -60 dB over the next 0.1 s
        const auto a = static_cast<std::size_t>(damp * sr);
        for (std::size_t i = a; i < n; ++i) out[i] *= std::pow(10.0, -3 * static_cast<double>(i - a) / (0.1 * sr));
    }
    return normalised(std::move(out), m.num("gain", 1));
}

// layers._filter_coeffs
Ba filter_coeffs(const std::string &kind, double f, double q, int sr) {
    f = std::min(std::max(f, 10.0), 0.45 * sr);
    if (kind == "band") return bandpass(f, f / std::max(q, 0.05), sr);
    const double w0 = 2 * PI * f / sr, cos = std::cos(w0), alpha = std::sin(w0) / (2 * std::max(q, 0.05)), a0 = 1 + alpha;
    Vec b;
    if (kind == "low")
        b = {(1 - cos) / 2, 1 - cos, (1 - cos) / 2};
    else if (kind == "high")
        b = {(1 + cos) / 2, -(1 + cos), (1 + cos) / 2};
    else
        throw std::runtime_error("unknown filter " + kind);
    for (double &v : b) v /= a0;
    return {b, {1.0, -2 * cos / a0, (1 - alpha) / a0}};
}

// layers.render_noise: noise through a moving filter
Vec noise_band(const Spec &p, int sr, uint64_t k) {
    const std::size_t n = samples(p.num("dur", 0), sr);
    Vec x = noise(key(k, "noise"), n);
    const std::string color = p.j.text("color", "white");
    if (color == "brown") {
        x = lfilter({1.0}, {1.0, -0.997}, x);
        const double top = peak(x) + 1e-12;
        for (double &v : x) v /= top;
    } else if (color != "white") {
        throw std::runtime_error("unknown noise color " + color);
    }
    const std::string kind = p.j.text("filter", "band");
    const double q = p.num("q", 1);
    std::vector<Ba> coeffs;
    for (double f : curve(p.rows("freq", {}, 2), (n + BLOCK - 1) / BLOCK, true)) coeffs.push_back(filter_coeffs(kind, f, q, sr));
    Vec y = time_varying(x, coeffs);
    Vec env = envelope(p.rows("amp", FLAT, 2), p.num("attack", 0.01), p.num("release", 0.05), n, sr);
    const Vec wobble = p.tuple("wobble", {0, 0});
    if (wobble[1]) {
        const Vec sn = smooth_noise(key(k, "wobble"), n, sr, wobble[0]);
        for (std::size_t i = 0; i < n; ++i) env[i] *= std::max(1 + wobble[1] * sn[i], 0.0);
    }
    for (std::size_t i = 0; i < n; ++i) y[i] = y[i] * env[i];
    return normalised(std::move(y), p.num("gain", 1));
}

// layers.render_scatter: seeded event times (thinning of the rate curve), a pop, drop or ping each
Vec scatter(const Spec &s, int sr, uint64_t k) {
    const double dur = s.num("dur", 0);
    const std::size_t n = samples(dur, sr);
    Vec out(n, 0.0);
    const Rows rate = s.rows("rate", {}, 2);
    Vec xs, ys;
    double top = -INFINITY;
    for (const Vec &r : rate) xs.push_back(r.at(0)), ys.push_back(r.at(1)), top = std::max(top, r.at(1));
    const double m = std::ceil(top * dur);   // event_times
    if (!(m > 0)) return out;
    Vec t = uniforms(key(k, "times"), static_cast<std::size_t>(m));
    std::sort(t.begin(), t.end());
    const Vec keep = uniforms(key(k, "keep"), t.size());
    Vec times;
    for (std::size_t i = 0; i < t.size(); ++i) {
        t[i] *= dur;
        if (keep[i] * top < interp(t[i] / dur, xs.data(), ys.data(), xs.size())) times.push_back(t[i]);
    }
    if (times.empty()) return out;
    const std::size_t M = times.size();
    const Vec uf = uniforms(key(k, "freq"), M), ud = uniforms(key(k, "decay"), M), ul = uniforms(key(k, "level"), M);
    const Vec freq = s.tuple("freq", {1000, 4000}), decay = s.tuple("decay", {0.002, 0.01}),
              level = s.tuple("level", {0.2, 1.0});
    const std::string event = s.j.text("event", "pop");
    for (std::size_t i = 0; i < M; ++i) {
        double f = freq[0] * std::pow(freq[1] / freq[0], uf[i]);
        const double d = decay[0] + (decay[1] - decay[0]) * ud[i], a = level[0] + (level[1] - level[0]) * ul[i];
        const auto start = static_cast<long long>(times[i] * sr);
        const long long L = std::min(std::max(static_cast<long long>(5 * d * sr), 8LL), static_cast<long long>(n) - start);
        if (L <= 0) continue;
        Vec ev(static_cast<std::size_t>(L)), env(ev.size());
        for (std::size_t j = 0; j < ev.size(); ++j) env[j] = std::exp(-(static_cast<double>(j) / sr) / d);
        if (event == "pop") {   // (at low sample rates a band past Nyquist folds down to just under it)
            f = std::min(f, 0.29 * sr);
            const Ba band = butter(2, 2 * (f / 1.5) / sr, 2 * std::min(f * 1.5, 0.45 * sr) / sr, 'b');
            ev = lfilter(band.b, band.a, noise(key(k, "ev", static_cast<uint64_t>(i)), ev.size()));
            for (std::size_t j = 0; j < ev.size(); ++j) ev[j] *= env[j];
        } else if (event == "drop") {   // a bubble: pitch rises as it shrinks
            for (std::size_t j = 0; j < ev.size(); ++j) {
                const double tt = static_cast<double>(j) / sr;
                ev[j] = std::sin(2 * PI * f * (tt + tt * tt / (4 * d))) * env[j];
            }
        } else if (event == "ping") {   // glassy: two inharmonic partials
            for (std::size_t j = 0; j < ev.size(); ++j) {
                const double tt = static_cast<double>(j) / sr;
                ev[j] = (std::sin(2 * PI * f * tt) + 0.4 * std::sin(2 * PI * 2.76 * f * tt) * env[j]) * env[j];
            }
        } else {
            throw std::runtime_error("unknown scatter event " + event);
        }
        for (std::size_t j = 0; j < ev.size(); ++j) out[start + j] += a * ev[j];
    }
    return normalised(std::move(out), s.num("gain", 1));
}

// -- the finishing chain -------------------------------------------------------------------------------------------

// render._room: a few dozen early reflections over ~60 ms (a sparse impulse response, summed directly)
void room(Vec &x, int sr, double mix, uint64_t k) {
    const auto n = static_cast<std::size_t>(0.06 * sr);
    Vec ir(n, 0.0);
    const Vec u = uniforms(key(k, "taps"), 40), g = noise(key(k, "gains"), 40);
    for (std::size_t i = 0; i < 40; ++i) {
        const auto tap = static_cast<std::size_t>(u[i] * static_cast<double>(n - 1));
        ir[tap] = g[i] * std::exp(-3 * static_cast<double>(tap) / static_cast<double>(n));
    }
    ir[0] = 1.0;
    std::vector<std::size_t> taps;
    for (std::size_t i = 0; i < n; ++i)
        if (ir[i] != 0) taps.push_back(i);
    Vec wet(x.size(), 0.0);
    for (std::size_t i = 0; i < x.size(); ++i)
        for (std::size_t t : taps) {
            if (t > i) break;
            wet[i] += ir[t] * x[i - t];
        }
    const double pw = peak(wet) + 1e-12, px = peak(x);
    for (std::size_t i = 0; i < x.size(); ++i) x[i] = (1 - mix) * x[i] + mix * wet[i] / pw * px;
}

// render._reverb: a decaying noise tail, by FFT convolution
void reverb(Vec &x, int sr, double seconds, double wet, uint64_t k) {
    const auto n = static_cast<std::size_t>(seconds * sr);
    Vec ir = noise(k, n);
    for (std::size_t i = 0; i < n; ++i) ir[i] *= std::exp(-6.9 * static_cast<double>(i) / static_cast<double>(n));
    sosfilt(butter(2, 5000 / (sr / 2.0), 0, 'l'), ir);
    Vec dry(x);
    dry.resize(x.size() + n, 0.0);
    // dry ends in n zeros, so a circular convolution as long as dry is already the linear one
    const std::size_t nfft = pocketfft::detail::util::good_size_real(dry.size());
    const std::ptrdiff_t R = sizeof(double), C = sizeof(cd);
    std::vector<double> a(nfft, 0.0), b(nfft, 0.0), tail(nfft);
    std::copy(dry.begin(), dry.end(), a.begin());
    std::copy(ir.begin(), ir.begin() + std::min(n, nfft), b.begin());
    std::vector<cd> A(nfft / 2 + 1), B(nfft / 2 + 1);
    pocketfft::r2c<double>({nfft}, {R}, {C}, 0, pocketfft::FORWARD, a.data(), A.data(), 1.0);
    pocketfft::r2c<double>({nfft}, {R}, {C}, 0, pocketfft::FORWARD, b.data(), B.data(), 1.0);
    for (std::size_t i = 0; i < A.size(); ++i) A[i] *= B[i];
    pocketfft::c2r<double>({nfft}, {C}, {R}, 0, pocketfft::BACKWARD, A.data(), tail.data(), 1.0 / nfft);
    tail.resize(dry.size());
    const double ratio = peak(x) / (peak(tail) + 1e-12);
    for (std::size_t i = 0; i < dry.size(); ++i) dry[i] = (1 - wet) * dry[i] + wet * tail[i] * ratio;
    x = std::move(dry);
}

// render._fold_loop: a seamless loop of `length` samples, the end cross-faded into the start, the rest wrapped
Vec fold_loop(const Vec &x, long long xfade, long long length) {
    length = std::max(std::min(length, static_cast<long long>(x.size())), 1LL);
    xfade = std::min({xfade, length, static_cast<long long>(x.size()) - length});
    Vec out(x.begin(), x.begin() + length);
    const Vec w = linspace(0.0, 1.0, static_cast<std::size_t>(std::max(xfade, 0LL)));
    for (long long i = 0; i < xfade; ++i)
        out[i] = out[i] * std::sin(0.5 * PI * w[i]) + x[length + i] * std::cos(0.5 * PI * w[i]);
    for (long long i = length + std::max(xfade, 0LL), j = 0; i < static_cast<long long>(x.size()); ++i, ++j)
        out[(std::max(xfade, 0LL) + j) % length] += x[i];
    return out;
}

thread_local std::string last_error;

}  // namespace
}  // namespace tune

using namespace tune;

extern "C" {

const char *tt_last_error(void) { return last_error.c_str(); }

int32_t tt_render_voice(const char *json, const tt_bank *const *banks, const char *const *names, int32_t n_banks,
                        int32_t sr, float **out, int32_t *n_out) {
    last_error.clear();
    if (!json || !out || !n_out || sr <= 0 || n_banks < 0 || (n_banks && (!banks || !names))) {
        last_error = "bad arguments";
        return 1;
    }
    try {
        const Json voice = Json::parse(json);
        if (voice.kind != Json::OBJ) throw std::runtime_error("a voice spec is a JSON object");
        const std::string format = voice.text("format", "tare.tools.tune.voice");
        if (format != "tare.tools.tune.voice" && format != "creaturesynth.voice")
            throw std::runtime_error("not a tare.tools.tune.voice document");
        if (voice.number("version", 6) > 6) throw std::runtime_error("the spec is newer than this core (version 6)");
        for (const char *other : {"chips", "speech", "vocoded"})
            if (!voice.list(other).empty())
                throw Unsupported(std::string("this core does not render ") + other + " layers yet");
        const Json *seed_v = voice.get("seed");
        const uint64_t seed = !seed_v ? 0 : seed_v->integer ? seed_v->whole : static_cast<uint64_t>(seed_v->num);

        std::vector<std::pair<long long, Vec>> parts;
        double duration = 0.0;
        const auto start = [&](const Spec &e) { return static_cast<long long>(e.num("start", 0) * sr); };
        const auto& syllables = voice.list("syllables");
        for (std::size_t i = 0; i < syllables.size(); ++i) {
            const Spec s{syllables[i]};
            parts.emplace_back(start(s), syllable(s, sr, key(seed, "syllable", static_cast<uint64_t>(i))));
            duration = std::max(duration, s.num("start", 0) + s.num("dur", 0));
        }
        const auto &spoken = voice.list("spoken");
        for (std::size_t i = 0; i < spoken.size(); ++i) {
            const Spec s{spoken[i]};
            const std::string name = s.j.text("bank", "");
            const tt_bank *bank = nullptr;
            for (int32_t b = 0; b < n_banks; ++b)
                if (names[b] && name == names[b]) bank = banks[b];
            if (!bank) {
                last_error = "no voice bank " + name + " was given";
                return 5;
            }
            const Rows pieces = s.rows("pieces", {}, 3);
            const Vec f0 = s.tuple("f0", {}), joins_d = s.tuple("joins", {});
            Vec flat;
            double frames = 0;
            for (const Vec &p : pieces) flat.insert(flat.end(), p.begin(), p.end()), frames += p.at(2);
            std::vector<int32_t> joins;
            for (double j : joins_d) joins.push_back(static_cast<int32_t>(j));
            double *y = nullptr;
            int32_t ny = 0;
            if (tt_render_spoken(bank, flat.data(), static_cast<int32_t>(pieces.size()), joins.data(),
                                 static_cast<int32_t>(joins.size()), f0.data(), static_cast<int32_t>(f0.size()),
                                 s.num("warp", 1), s.num("breath", 0), s.num("tilt", 0), s.num("gain", 1),
                                 key(seed, "spoken", static_cast<uint64_t>(i)), sr, &y, &ny) != 0)
                throw std::runtime_error("cannot render spoken layer " + std::to_string(i));
            parts.emplace_back(start(s), Vec(y, y + ny));
            tt_free(y);
            duration = std::max(duration, s.num("start", 0) + frames * 0.005);
        }
        for (const char *name : {"modal", "noise", "scatter"}) {
            const auto &layers = voice.list(name);
            for (std::size_t i = 0; i < layers.size(); ++i) {
                const Spec e{layers[i]};
                const uint64_t k = key(seed, name, static_cast<uint64_t>(i));
                parts.emplace_back(start(e), name[0] == 'm'   ? modal(e, sr, k)
                                             : name[0] == 'n' ? noise_band(e, sr, k)
                                                              : scatter(e, sr, k));
                duration = std::max(duration, e.num("start", 0) + e.num("dur", 0));
            }
        }
        if (parts.empty()) throw std::runtime_error("the voice has no layers");

        std::size_t length = 0;
        for (const auto &[at, y] : parts) length = std::max(length, static_cast<std::size_t>(at) + y.size());
        Vec x(length, 0.0);
        for (const auto &[at, y] : parts)
            for (std::size_t i = 0; i < y.size(); ++i) x[at + i] += y[i];
        sosfilt(butter(2, 40 / (sr / 2.0), 0, 'h'), x);
        double p = peak(x) + 1e-12;
        for (double &v : x) v /= p;
        if (const double crush = voice.number("crush", 0)) {   // render._crush: hold every `hold` samples, fewer levels
            const std::size_t hold = 1 + static_cast<std::size_t>(crush * 11);
            const double levels = std::pow(2.0, 14 - 10 * crush);
            const Vec held = x;
            for (std::size_t i = 0; i < x.size(); ++i) x[i] = std::nearbyint(held[i - i % hold] * levels) / levels;
        }
        if (const double drive = voice.number("drive", 0))
            for (double &v : x) v = std::tanh(drive * v) / std::tanh(drive);
        if (const double bits = voice.number("bits", 0)) {   // render._grain: an adaptive quantizer
            const double a = 1 - std::exp(-1 / (0.005 * sr));
            Vec mag(x.size());
            for (std::size_t i = 0; i < x.size(); ++i) mag[i] = std::abs(x[i]);
            const Vec env = lfilter({a}, {1.0, a - 1}, mag);
            for (std::size_t i = 0; i < x.size(); ++i) {
                const double q = std::max(env[i] * std::pow(2.0, 1 - bits), 0x1p-15);
                x[i] = std::nearbyint(x[i] / q) * q;
            }
        }
        if (const double lowpass = voice.number("lowpass", 0))
            sosfilt(butter(2, std::min(lowpass, 0.45 * sr) / (sr / 2.0), 0, 'l'), x);
        if (const double mix = voice.number("room", 0)) room(x, sr, mix, key(seed, "room"));
        if (const double air = voice.number("air", 0)) {
            Vec pink = noise(key(seed, "air"), x.size());
            sosfilt(butter(1, 1000 / (sr / 2.0), 0, 'l'), pink);
            const double pp = peak(pink) + 1e-12, level = std::pow(10.0, (-70 + 40 * air) / 20);
            for (std::size_t i = 0; i < x.size(); ++i) x[i] = x[i] + pink[i] / pp * level;
        }
        if (const double space = voice.number("space", 0)) reverb(x, sr, space, voice.number("wet", 0.2), key(seed, "space"));
        if (const double loop = voice.number("loop", 0)) {
            x = fold_loop(x, static_cast<long long>(loop * sr), static_cast<long long>(std::nearbyint((duration - loop) * sr)));
        } else {
            const std::size_t fade = std::min(static_cast<std::size_t>(0.004 * sr), x.size());
            const Vec w = linspace(1.0, 0.0, fade);
            for (std::size_t i = 0; i < fade; ++i) x[x.size() - fade + i] *= w[i];
        }
        p = peak(x) + 1e-12;
        const double gain = voice.number("gain", 1);
        auto *buf = static_cast<float *>(std::malloc(x.size() * sizeof(float)));
        if (!buf) {
            last_error = "out of memory";
            return 2;
        }
        for (std::size_t i = 0; i < x.size(); ++i) buf[i] = static_cast<float>(PEAK * gain * x[i] / p);
        *out = buf;
        *n_out = static_cast<int32_t>(x.size());
        return 0;
    } catch (const Unsupported &e) {
        last_error = e.what();
        return 4;
    } catch (const std::bad_alloc &) {
        last_error = "out of memory";
        return 2;
    } catch (const std::exception &e) {
        last_error = e.what();
        return 1;
    }
}

}  // extern "C"
