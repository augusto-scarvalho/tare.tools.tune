/* tare.tools.tune, native core: the renderer, for engines that cannot run Python.
 *
 * Python designs a sound (a sword hit, a menu tick, a creature's call, a planned line of speech) into a voice spec,
 * plain JSON; this renders it, the same sound as src/tare/tools/tune/render.py, deterministically.
 * Reading banks and specs from files is the engine wrapper's job.
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
 * that cross-fade with the one before; `f0` the pitch along the line; `rough` and `sub` (0..1) a hoarse voice and
 * a doubled one. Peak-normalised to `gain`. On success returns 0 and a buffer of *n_out samples to release with
 * tt_free. */
TT_API int32_t tt_render_spoken(const tt_bank *bank, const double *pieces, int32_t n_pieces, const int32_t *joins,
                                int32_t n_joins, const double *f0, int32_t n_f0, double warp, double breath,
                                double tilt, double rough, double sub, double gain, uint64_t seed,
                                int32_t sample_rate, double **out, int32_t *n_out);

/* A whole voice spec, as Voice.to_json() writes it: render.render(voice, sample_rate), float samples peaking at
 * -1 dBFS x gain. `knobs` (NULL or "" for none) is a JSON object that turns the general knobs of sfx/knobs.py over
 * the spec first, as Python would: {"register": -1, "tempo": 1.5} (register, tempo, length, ring, brightness,
 * sparkle). Spoken layers find their voice bank by name in `names` (n_banks of them, with `banks`).
 * Returns 0 and a buffer of *n_out samples to release with tt_free; otherwise tt_last_error() says why:
 * 1 a bad argument or spec, 2 out of memory, 4 a layer this core does not render yet (chip programs, formant speech,
 * vocoded clips), 5 a spoken layer whose bank was not given. */
TT_API int32_t tt_render_voice(const char *json, const char *knobs, const tt_bank *const *banks,
                               const char *const *names, int32_t n_banks, int32_t sample_rate, float **out,
                               int32_t *n_out);

/* Why the last tt_render_voice on this thread failed ("" if it did not). */
TT_API const char *tt_last_error(void);

TT_API void tt_free(void *buffer);

#ifdef __cplusplus
}
#endif

#endif
