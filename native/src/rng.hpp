// SplitMix64 + FNV-1a, exactly as src/tare/tools/tune/rng.py (its test vectors: tests/test_rng_genome.py).
#pragma once

#include <cstdint>
#include <string_view>
#include <vector>

namespace tune {

inline constexpr uint64_t GOLDEN = 0x9E3779B97F4A7C15ULL;

inline uint64_t fmix(uint64_t z) {
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

inline uint64_t fnv1a(std::string_view text) {
    uint64_t h = 0xCBF29CE484222325ULL;
    for (unsigned char c : text) h = (h ^ c) * 0x100000001B3ULL;
    return h;
}

// rng.key(*parts): integers as they are, strings by FNV-1a
inline uint64_t fold(uint64_t h, uint64_t part) { return fmix((h ^ part) + GOLDEN); }
inline uint64_t fold(uint64_t h, std::string_view part) { return fold(h, fnv1a(part)); }
inline uint64_t fold(uint64_t h, const char *part) { return fold(h, fnv1a(part)); }
inline uint64_t fold(uint64_t h, int part) { return fold(h, static_cast<uint64_t>(part)); }

template <class... Parts>
uint64_t key(Parts... parts) {
    uint64_t h = 0;
    ((h = fold(h, parts)), ...);
    return h;
}

// rng.noise(k, n): white noise in [-1, 1), element i = fmix(k + (i + 1) * GOLDEN)
inline void noise(uint64_t k, std::size_t n, std::vector<double> &out) {
    out.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const uint64_t z = fmix(k + static_cast<uint64_t>(i + 1) * GOLDEN);
        out[i] = static_cast<double>(z >> 11) * 0x1p-53 * 2.0 - 1.0;
    }
}

}  // namespace tune
