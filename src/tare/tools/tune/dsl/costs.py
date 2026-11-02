"""Conservative sample-work and temporary-allocation estimates before synthesis."""

import math

from .model import DSLError
from .registry import COLLECTIONS


def preflight(plan, budget):
    seen = set()
    graph_counts = {}
    actual_layers = 0

    def graph_parts(value):
        if id(value) in graph_counts:
            return graph_counts[id(value)]
        if value.kind == "voice":
            count = sum(len(getattr(value.source, collection)) for collection in COLLECTIONS.values())
        elif value.kind in ("score", "cue"):
            score = value.source.score if value.kind == "cue" else value.source
            if len(score.tracks) > budget.limits.tracks or any(
                len(t.events) > budget.limits.notes for t in score.tracks.values()
            ):
                raise DSLError(
                    "E_LIMIT", "generated Score track/note budget exceeded", value.origins.get("pointer", "")
                )
            count = sum(len(t.layers) + bool(t.layers) for t in score.tracks.values()) + len(score.sounds)
        else:
            count = 1
        count += len(value.placements) + sum(graph_parts(p["plan"]) for p in value.placements)
        if count > budget.limits.layers:
            raise DSLError("E_LIMIT", "projected capture part/layer budget exceeded", value.origins.get("pointer", ""))
        graph_counts[id(value)] = count
        return count

    def layers(items, sr, at):
        nonlocal actual_layers
        actual_layers += len(items)
        end = 0
        retained_frames, largest_layer = 0, 0
        for layer in items:
            duration = getattr(layer, "dur", None)
            if duration is None:
                if type(layer).__name__ == "ChipProgram":
                    from ..chip import program_duration

                    duration = program_duration(layer)
                else:
                    duration = layer.duration
            end = max(end, layer.start + duration)
            frames = max(16, math.ceil(duration * sr))
            retained_frames += frames
            largest_layer = max(largest_layer, frames)
            work = frames * (1 + len(getattr(layer, "modes", [])) + len(getattr(layer, "formants", [])))
            if hasattr(layer, "hits"):
                for when, _, contact in layer.hits:
                    if when < duration:
                        extra = math.ceil(contact * sr)
                        if extra * 8 * 4 > budget.limits.work_bytes:
                            raise DSLError("E_LIMIT", "modal contact temporary allocation exceeds work budget", at)
                        work += extra
                _, scrape_duration, gain, _ = layer.scrape
                if gain:
                    extra = math.ceil(scrape_duration * sr)
                    if extra * 8 * 4 > budget.limits.work_bytes:
                        raise DSLError("E_LIMIT", "modal scrape temporary allocation exceeds work budget", at)
                    work += extra
            if type(layer).__name__ == "Scatter":
                event_count = math.ceil(max(point[1] for point in layer.rate) * duration) + 1
                if event_count * 8 * 12 > budget.limits.work_bytes:
                    raise DSLError("E_LIMIT", "scatter events exceed working memory budget", at)
                work += event_count * min(frames, max(8, math.ceil(5 * max(layer.decay) * sr)))
            budget.charge("weighted_work", work, at)
        # Layer buffers contain their own durations, not a full track-length
        # padded buffer each. Avoid multiplying end time by note count.
        end_frames = math.ceil(end * sr)
        budget.audio(end_frames, sr, layers=1, pointer=at)
        estimate = retained_frames * 8 + largest_layer * 8 * 8 + end_frames * 8 * 4
        if estimate > budget.limits.work_bytes:
            raise DSLError("E_LIMIT", "estimated layer buffers exceed working memory budget", at)

    def visit(value):
        if id(value) in seen:
            return
        seen.add(id(value))
        at = value.origins.get("pointer", "")
        if value.kind == "voice":
            layers(
                [layer for collection in COLLECTIONS.values() for layer in getattr(value.source, collection)],
                value.sr,
                at,
            )
        elif value.kind in ("score", "cue"):
            score = value.source.score if value.kind == "cue" else value.source
            for track in score.tracks.values():
                layers(track.layers, value.sr, at)
            if value.loop is not None and value.loop > budget.limits.seconds:
                raise DSLError("E_LIMIT", "Score loop exceeds duration budget", at)
        else:
            duration = value.source.get("duration", 0.6) if value.kind == "fm" else float(value.span or 0)
            budget.charge("weighted_work", math.ceil(duration * value.sr) * (8 if value.kind == "fm" else 1), at)
        for placement in value.placements:
            visit(placement["plan"])

    projected = graph_parts(plan)
    visit(plan)
    return {"projected_capture_parts": projected, "actual_layers": actual_layers}
