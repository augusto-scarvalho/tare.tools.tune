// The source-filter vocoder of src/tare/tools/tune/speech/vocoder.py (WORLD-style synthesis), in C++.
#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace tune {

inline constexpr double FRAME = 0.005;        // seconds per frame
inline constexpr int AP_BANDS = 5;
inline constexpr double ENV_FLOOR = -107.5;   // envelopes are stored in 0.5 dB steps from here
inline constexpr double BREATH = 1.7320508075688772;   // 3 ** 0.5
inline constexpr double UNVOICED = 500.0;     // Hz: the pulse rate where there is no voice
inline constexpr double ROUGH_CENTS = 45.0, ROUGH_DB = 1.7;   // rough = 1: periods ~45 cents off, pulses ~1.7 dB
inline constexpr double SUB_DIP = 0.8, SUB_SHIFT = 0.04;      // sub = 1: every other pulse 80 % weaker, 4 % sooner

// vocoder.Template: what a recording leaves once analysed, every 5 ms
struct Clip {
    std::vector<double> f0;    // Hz, 0 = no voice
    std::vector<double> env;   // frames x bands, dB
    std::vector<double> ap;    // frames x 5, 0..1
    int bands = 0;
    double pitch = 0.0;        // median pitch of the voiced frames (only `swing` uses it)
    std::size_t frames() const { return f0.size(); }
};

// numpy.interp for increasing xp, clamped to the end values
double interp(double x, const double *xp, const double *fp, std::size_t m);

// vocoder.synthesize: the clip's sound, moved to another voice, deterministic for a seed
std::vector<double> synthesize(const Clip &clip, int sr, double pitch = 1.0, double warp = 1.0, double stretch = 1.0,
                               double breath = 0.0, double tilt = 0.0, double swing = 1.0, uint64_t seed = 0,
                               double rough = 0.0, double sub = 0.0);

}  // namespace tune
