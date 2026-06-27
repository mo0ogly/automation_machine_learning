"""
Build sample-independent TEXT features for the AEGIS augmented set, to test whether
richer features unlock the finer label levels (target_delta, family_l2,
technique_l3) under GROUP-aware evaluation.

Two feature sets, both **independent per sample** (no corpus-fit), so a single saved
matrix is leak-free under GroupKFold and the notebook never needs the raw text:
  - emb   : sentence-transformer embeddings (frozen pretrained model) — best effort,
            skipped if the model cannot be loaded offline.
  - hash  : HashingVectorizer char n-grams (3-5), stateless -> no vocabulary leakage.

SAFETY: templates are instantiated and vectorised entirely in-script; the raw attack
text is NEVER written to disk or printed. Only numeric matrices + labels are saved.

Outputs (data/aegis_text_features/):
  labels.csv   label,target_delta,family_l2,technique_l3,template_group
  hash.npz     scipy sparse CSR, HashingVectorizer char(3,5), 2**18 dims
  emb.npy      dense float32 [N, d]  (only if sentence-transformers loads)

Run:
    python data/generators/build_aegis_text_features.py
"""
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import HashingVectorizer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generators"))
import prompt_injection_aegis_aug as aug  # reuse pools / fillers / taxonomy maps

OUT = ROOT / "aegis_text_features"
OUT.mkdir(exist_ok=True)


def instantiate(per_template=64, seed=42):
    """Re-create (text, labels) pairs deterministically. Text stays in memory."""
    random.seed(seed)
    rng = random.Random(seed)
    tech2fam, tech2cls = aug._cs_maps()
    texts, labels = [], []

    def add(text, lbl):
        texts.append(text)
        labels.append(lbl)

    for fp in sorted((aug.POC / "prompts").glob("*.json")):
        try:
            import json
            o = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(o, dict) or not isinstance(o.get("template"), str):
            continue
        tx = o.get("taxonomy") or {}
        primary = tx.get("primary") if isinstance(tx, dict) else None
        variables = o.get("variables") or {}
        is_benign = (primary in aug.BENIGN_PRIMARIES) or (o.get("category") == "benign")
        lbl = {
            "label": "benign" if is_benign else "injection",
            "target_delta": (o.get("target_delta") or "").split("_")[0] or None,
            "family_l2": tech2fam.get(primary, "extension"),
            "technique_l3": primary,
            "template_group": fp.stem,
        }
        varied = [s for s in variables if s in aug.POOLS and s not in aug.ATTACK_SLOTS]
        cap = per_template if varied else 1
        seen, made, attempts = set(), 0, 0
        while made < cap and attempts < cap * 4 + 4:
            attempts += 1
            text = aug._fill(o["template"], variables, rng)
            obf = "none" if made == 0 else rng.choices(list(aug.OBFS), weights=[5, 2, 2, 1, 1])[0]
            text = aug.OBFS[obf](text)
            k = hash(text)
            if k in seen:
                continue
            seen.add(k)
            made += 1
            add(text, lbl)

    # benign clinical rows (same patterns as the CSV)
    per = max(1, 3800 // len(aug.BENIGN_TEMPLATES))
    import re
    for gi, tmpl in enumerate(aug.BENIGN_TEMPLATES):
        slots = re.findall(r"\{([A-Z_]+)\}", tmpl)
        seen, made, attempts = set(), 0, 0
        while made < per and attempts < per * 4 + 4:
            attempts += 1
            text = tmpl
            for s in slots:
                text = text.replace("{" + s + "}", rng.choice(aug.POOLS.get(s, ["n/a"])))
            k = hash(text)
            if k in seen:
                continue
            seen.add(k)
            made += 1
            add(text, {"label": "benign", "target_delta": None, "family_l2": "benign",
                       "technique_l3": "clean_clinical_query", "template_group": "benign_%02d" % gi})
    return texts, pd.DataFrame(labels)


SURFACE_COLS = ["text_length", "word_count", "avg_word_length", "max_token_length",
                "uppercase_ratio", "digit_ratio", "punct_ratio", "line_count",
                "non_ascii_ratio", "zero_width_count", "url_count",
                "trigger_keyword_count", "role_keyword_count",
                "delimiter_marker_count", "has_base64_blob"]


def main():
    sys.path.insert(0, str(ROOT / "generators"))
    from prompt_injection import features
    texts, labels = instantiate()
    labels.to_csv(OUT / "labels.csv", index=False, encoding="utf-8")
    print("samples:", len(texts))

    # surface features (the 15 baseline), saved numeric so the notebook needs no text
    Xs = pd.DataFrame([features(t) for t in texts])[SURFACE_COLS].to_numpy("float32")
    np.save(OUT / "surface.npy", Xs)
    print("surface features:", Xs.shape, "-> surface.npy")

    hv = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                           n_features=2 ** 18, alternate_sign=False, norm="l2")
    Xh = hv.transform(texts)  # stateless: no fit -> leak-free
    sparse.save_npz(OUT / "hash.npz", Xh)
    print("hash features:", Xh.shape, "-> hash.npz")

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(texts, batch_size=64, show_progress_bar=False,
                           normalize_embeddings=True).astype("float32")
        np.save(OUT / "emb.npy", emb)
        print("embeddings:", emb.shape, "-> emb.npy")
    except Exception as e:
        print("embeddings skipped (model unavailable offline):", str(e)[:80])


if __name__ == "__main__":
    main()
