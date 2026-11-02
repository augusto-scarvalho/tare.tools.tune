import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from curate import Round, agree, answers_json, compare_bundles, main, predict, serve, summary  # noqa: E402


def test_a_round_is_served_and_its_answers_kept(tmp_path):
    r = Round("teste", title="Teste", blind=True, root=tmp_path)
    g = r.group("tons", tasks=["pick", "rate:robótico", "abx:grave|agudo", "marks", "notes"], reference="grave",
                targets={"hz": 220})
    t = np.arange(4410) / 44100
    g.add("grave", 0.5 * np.sin(2 * np.pi * 220 * t), sr=44100, metrics={"hz": 220})
    g.add("agudo", 0.5 * np.sin(2 * np.pi * 440 * t), sr=44100, metrics={"hz": 440})
    r.save()
    server = serve(tmp_path, 0, open_browser=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"<title>Curadoria</title>" in urllib.request.urlopen(base + "/").read()
        assert json.loads(urllib.request.urlopen(base + "/api/rounds").read())[0]["name"] == "teste"
        m = json.loads(urllib.request.urlopen(base + "/api/round/teste").read())["manifest"]
        g0 = m["groups"][0]
        seg = g0["segments"]
        assert g0["reference"] == seg[0]["id"] and g0["tasks"][2]["x"] in (seg[0]["id"], seg[1]["id"])
        assert urllib.request.urlopen(f"{base}/files/teste/{seg[1]['file']}").read()[:4] == b"RIFF"
        answers = {"g1": {"pick": seg[1]["id"], "rate:robótico": {seg[0]["id"]: 2}, "notes": "ok",
                          "marks": [{"seg": seg[0]["id"], "t": 0.05, "note": "aqui"}]}}
        req = urllib.request.Request(f"{base}/api/round/teste/answers", json.dumps(answers).encode(), method="POST")
        assert json.loads(urllib.request.urlopen(req).read())["ok"]
        assert json.loads((tmp_path / "teste" / "answers.json").read_text(encoding="utf-8")) == answers
        assert "pick: agudo" in summary("teste", tmp_path) and "grave @ 0.05s aqui" in summary("teste", tmp_path)
        for bad in ("/files/teste/../../secret", "/files/..%2F/teste", "/api/round/..%2Fteste"):
            try:
                urllib.request.urlopen(base + bad)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code == 404
    finally:
        server.shutdown()


def test_revisions_old_tabs_stale_rounds_and_exact_blind_audio(tmp_path):
    from tare.tools.tune import capture
    from tare.tools.tune.bundles import save_bundle
    a = save_bundle(capture(np.ones(100, dtype=np.float32) * 0.1, 16000), tmp_path / "bundles")
    b = save_bundle(capture(np.ones(100, dtype=np.float32) * 0.2, 16000), tmp_path / "bundles")
    path = compare_bundles("blind", a, b, root=tmp_path / "rounds")
    old = json.loads(path.read_text())
    revision = old["revision"]
    retained = path.parent / old["groups"][0]["segments"][0]["file"]
    assert retained.read_bytes() == (a / "audio.wav").read_bytes()
    compare_bundles("blind", b, a, root=tmp_path / "rounds")
    assert retained.read_bytes() == (a / "audio.wav").read_bytes()
    current = json.loads(path.read_text())["revision"]
    server = serve(tmp_path / "rounds", 0, open_browser=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        document = {"revision": revision, "version": 0, "answers": {"g1": {"notes": "old tab"}}}
        def post(value):
            req = urllib.request.Request(base + "/api/round/blind/answers", json.dumps(value).encode())
            return json.loads(urllib.request.urlopen(req).read())
        assert post(document)["version"] == 1
        with pytest.raises(urllib.error.HTTPError) as error:
            post(document)
        assert error.value.code == 409
        assert json.loads(path.read_text())["revision"] == current
        assert json.loads((path.parent / "answers.json").read_text()) == {}
        historical = json.loads(urllib.request.urlopen(base + f"/api/round/blind?revision={revision}").read())
        assert historical["answers"] == document["answers"]
    finally:
        server.shutdown()
        server.server_close()
    stale = Round("race", root=tmp_path)
    stale.group("old").add("old", np.zeros(100), sr=16000)
    newer = Round("race", root=tmp_path)
    newer.group("new").add("new", np.zeros(100), sr=16000)
    latest = newer.save().read_bytes()
    with pytest.raises(ValueError, match="stale"):
        stale.save()
    assert (tmp_path / "race" / "manifest.json").read_bytes() == latest


def test_review_candidates_go_to_the_ear_and_the_pick_is_what_gets_committed(tmp_path):
    from tare.tools.tune.bundles import load_bundle
    from tare.tools.tune.dsl import builders as t
    from tare.tools.tune.dsl import edit_file, review
    src, out, rounds = tmp_path / "bank.tune.json", tmp_path / "reviews", tmp_path / "rounds"
    t.Project(context={"sample_rate": 16000},
              sounds={"confirm": t.sfx("ui", style="crystal", event="confirm", dry=True)}).write(src)
    a = review(src, name="confirm", output=out)["bundle"]
    b, c = (edit_file(src, from_bundle=a, output=out, set_fields={"/power": p}, dry_run=True)["bundle"]
            for p in (0.9, 0.2))
    with pytest.raises(ValueError, match="2 to 9"):
        compare_bundles("one", a, root=rounds)
    path = compare_bundles("power", a, b, c, root=rounds, blind=False, question="qual soa mais firme?")
    group = json.loads(path.read_text(encoding="utf-8"))["groups"][0]
    assert [x["type"] for x in group["tasks"]] == ["pick", "rate", "marks", "notes"]
    assert group["note"] == "qual soa mais firme?"
    seg = group["segments"]
    assert seg[0]["note"] == "confirm" and seg[1]["note"] == "confirm\n/power: added 0.9"
    assert seg[0]["metrics"]["duration_s"] > 0 and seg[0]["metrics"]["peak_dbfs"] < 0
    ids, rate = [x["id"] for x in seg], group["tasks"][1]["id"]
    (path.parent / "answers.json").write_text(json.dumps({"g1": {
        "pick": ids[2], rate: {ids[0]: 2, ids[2]: 5}, "marks": [{"seg": ids[1], "t": 0.1, "note": "clique"}]}}))
    got = answers_json("power", rounds)["groups"][0]
    assert got["answers"] == {"pick": "C", rate: {"A": 2, "C": 5},
                              "marks": [{"seg": "B", "t": 0.1, "note": "clique"}]}
    assert got["segments"] == {k: str(Path(v).resolve()) for k, v in zip("ABC", (a, b, c), strict=True)}
    # A dry-run pick re-applied from the still-fresh observation commits exactly the audio that was heard.
    applied = edit_file(src, from_bundle=a, output=out, set_fields={"/power": 0.2})["bundle"]
    assert load_bundle(applied).manifest["pcm_id"] == load_bundle(got["segments"]["C"]).manifest["pcm_id"]

    blind = compare_bundles("abx", a, b, root=rounds)
    x = json.loads(blind.read_text())["groups"][0]["tasks"][0]["x"]
    (blind.parent / "answers.json").write_text(json.dumps({"g1": {"abx:A|B": {"answer": x}}}))
    assert answers_json("abx", rounds)["groups"][0]["answers"]["abx:A|B"]["correct"] is True
    # A level question opens without loudness matching; other rounds keep the old manifest (no key).
    assert "match" not in json.loads(blind.read_text())
    assert json.loads(compare_bundles("levels", a, b, root=rounds, keep_levels=True).read_text())["match"] is False
    # A recording beside the candidates: REF first and diffed against, its measures the targets, the round open
    # (blind would hide it), and the answers name its file.
    from tare.tools.tune.audio_io import write_wav
    write_wav(tmp_path / "ref.wav", load_bundle(c).audio * 0.5, 16000)
    path = compare_bundles("ref", a, b, root=rounds, reference=tmp_path / "ref.wav")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    group, ref = manifest["groups"][0], manifest["groups"][0]["segments"][0]
    assert not manifest["blind"] and ref["label"] == "REF" and group["reference"] == ref["id"]
    assert {"active_s", "centroid_hz"} <= set(group["targets"])
    assert group["targets"]["active_s"] == ref["metrics"]["active_s"]
    assert all("centroid_hz" in s["metrics"] for s in group["segments"])
    (path.parent / "answers.json").write_text(json.dumps({"g1": {"pick": group["segments"][2]["id"]}}))
    got = answers_json("ref", rounds)["groups"][0]
    assert got["answers"] == {"pick": "B"} and got["segments"]["REF"] == str((tmp_path / "ref.wav").resolve())


def test_a_prediction_comes_before_the_listening_and_agree_scores_it(tmp_path, capsys):
    t = np.arange(8000) / 16000

    def tone(hz, tau):
        return 0.5 * np.sin(2 * np.pi * hz * t) * np.exp(-t / tau)

    near, bright, long = tone(1000, 0.1), tone(2500, 0.1), tone(1000, 0.4)

    def make(name, *candidates):
        r = Round(name, root=tmp_path)
        g = r.group("perto", tasks=["pick", "rate:perto|longe|igual"], reference="REF", targets={"active_s": 0.3})
        for label, y in (("REF", tone(1000, 0.1) * 0.7), *zip("ABC", candidates, strict=True)):
            g.add(label, y, sr=16000)
        pair = r.group("par", tasks=["abx:A|B"])
        pair.add("A", near, sr=16000)
        pair.add("B", near * 0.9, sr=16000)
        return json.loads(r.save().read_text(encoding="utf-8"))

    def listen(name, manifest, pick, rates):
        g1, g2 = manifest["groups"]
        ids = {s["label"]: s["id"] for s in g1["segments"]}
        answers = {"g1": {"pick": ids[pick], g1["tasks"][1]["id"]: {ids[k]: v for k, v in rates.items()}},
                   "g2": {"abx:A|B": {"answer": g2["tasks"][0]["x"]}}}
        body = {"revision": manifest["revision"], "version": 0, "answers": answers}
        req = urllib.request.Request(f"{base}/api/round/{name}/answers", json.dumps(body).encode(), method="POST")
        assert json.loads(urllib.request.urlopen(req).read())["ok"]

    server = serve(tmp_path, 0, open_browser=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        one = make("um", near, bright, long)
        for bad in ({"g9": {}}, {"g1": {"pick": "Z"}}, {"g1": {"rate": {"A": 7}}}, {"g2": {"distinguishable": 1}}):
            with pytest.raises(ValueError):
                predict("um", bad, tmp_path)
        reading = {"g1": {"pick": "A", "rate": {"A": 5, "B": 1, "C": 3}, "evidence": "A: = everywhere"},
                   "g2": {"distinguishable": False}}
        predict("um", reading, tmp_path)
        listen("um", one, "A", {"A": 5, "B": 1, "C": 4})
        with pytest.raises(ValueError, match="already has answers"):
            predict("um", reading, tmp_path)
        report = agree("um", tmp_path)
        assert report["pick"] == {"n": 1, "assistant": 1, "numeric_rule": [1, 1], "chance": 0.33, "lucky": 0.3333}
        assert report["rate"] == {"n": 3, "spearman": 1.0}
        assert report["abx"] == {"n": 1, "assistant": 0, "chance": 0.5, "lucky": 1.0}  # the listener told them apart
        assert report["listener_repeats"] == {"n": 0, "same_pick": 0}
        # The same sounds again, shuffled under new labels: the listener's own consistency.
        two = make("dois", long, near, bright)
        predict("dois", {"g1": {"pick": "B"}}, tmp_path)
        listen("dois", two, "B", {})
        again = agree("dois", tmp_path)
        assert again["listener_repeats"] == {"n": 1, "same_pick": 1} and again["groups"][0]["rule"] == "B"
        both = agree(["um", "dois"], tmp_path)
        assert both["pick"]["n"] == 2 and both["pick"]["lucky"] == round(1 / 9, 4)  # two right by luck: 1 in 9
        main(["agree", "um", "dois", "--root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "same pick as in another group of the same sounds 2/2" in out and "a guesser does as well 11.1%" in out
        late = tmp_path / "dois" / "predictions" / f"{two['revision']}.json"
        late.write_text(json.dumps({"revision": two["revision"], "groups": {"g1": {"pick": "B"}}}))
        with pytest.raises(ValueError, match="after the first answer"):
            agree("dois", tmp_path)
    finally:
        server.shutdown()
