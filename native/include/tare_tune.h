/* tare.tools.tune, native core: the natural voice's vocoder, for engines that cannot run Python.
 *
 * Python plans a line (text -> phones -> melody -> pieces of a voice bank) into a small spec, a `Spoken` layer;
 * this renders it, the same sound as src/tare/tools/tune/speech/concat.py:render_spoken, deterministically.
 * Arrays in, arrays out: reading banks and specs from files is the engine wrapper's job.
 */
#ifndef TARE_TUNE_H
#define TARE_TUNE_H

#include <stdint.h>

#if defined(TARE_TUNE_STATIC)   /* compiled into something else (the Godot extension) */
#define TT_API
#elif defined(_WIN32) && defined(TARE_TUNE_BUILD)
#define TT_API __declspec(dllexport)
#elif defined(_WIN32)
#define TT_API __declspec(dllimport)
#elif defined(__GNUC__)
#define TT_API __attribute__((visibility("default")))
#else
#define TT_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct tt_bank tt_bank;

/* A voice bank's frames (5 ms each): pitch in Hz (0 = no voice), the spectral envelope in `bands` bands as stored
 * (0.5 dB steps above -107.5 dB, NOT frame-to-frame deltas) and the aperiodicity in 5 bands (0..255). Copied. */
TT_API tt_bank *tt_bank_new(int32_t frames, int32_t bands, const float *f0, const uint8_t *env, const uint8_t *ap);
TT_API void tt_bank_free(tt_bank *bank);

/* rng.key(seed, label) or, with index >= 0, rng.key(seed, label, index). A Voice renders its i-th spoken layer
 * with tt_key(voice.seed, "spoken", i). */
TT_API uint64_t tt_key(uint64_t seed, const char *label, int64_t index);

/* One Spoken layer: `pieces` is n_pieces x (bank frame from, bank frame to, output frames); `joins` the pieces
 * that cross-fade with the one before; `f0` the pitch along the line. Peak-normalised to `gain`. On success
 * returns 0 and a buffer of *n_out samples to release with tt_free. */
TT_API int32_t tt_render_spoken(const tt_bank *bank, const double *pieces, int32_t n_pieces, const int32_t *joins,
                                int32_t n_joins, const double *f0, int32_t n_f0, double warp, double breath,
                                double tilt, double gain, uint64_t seed, int32_t sample_rate, double **out,
                                int32_t *n_out);

/* A Voice's finishing, in place, over its layers already mixed at their start times: a 40 Hz high-pass, crush,
 * drive, a 4 ms fade-out and the peak at -1 dBFS x gain (render.py). Reverb ("space") is left to the engine. */
TT_API int32_t tt_finish(double *samples, int32_t n, int32_t sample_rate, double gain, double crush, double drive);

TT_API void tt_free(void *buffer);

#ifdef __cplusplus
}
#endif

#endif
