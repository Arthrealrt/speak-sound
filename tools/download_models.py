"""Explicit online provisioning; the app itself never downloads models."""
import argparse
import hashlib
import os
from pathlib import Path
import time

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)

from huggingface_hub import snapshot_download, hf_hub_url, get_hf_file_metadata
import requests

ROOT = Path(__file__).resolve().parent.parent


def download_weights(repo, folder, revision="main", expected_hash=None, filename="model.bin"):
    """Resumable download with small chunks and visible progress on slow links."""
    url = hf_hub_url(repo, filename, revision=revision)
    meta = get_hf_file_metadata(url)
    expected_hash = expected_hash or (meta.etag if len(meta.etag or "") == 64 else None)
    folder.mkdir(parents=True, exist_ok=True)
    final, partial = folder / filename, folder / (filename + ".part")
    if final.exists() and final.stat().st_size == meta.size:
        with final.open("rb") as handle:
            verified = not expected_hash or hashlib.file_digest(handle, "sha256").hexdigest() == expected_hash
        if verified:
            print(f"Verified existing weights: {repo}", flush=True)
            return
    for attempt in range(5):
        offset = partial.stat().st_size if partial.exists() else 0
        try:
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            with requests.get(url, params={"download": "true"}, headers=headers,
                              stream=True, timeout=(15, 30)) as response:
                response.raise_for_status()
                if response.status_code != 206:
                    offset = 0
                mode = "ab" if offset else "wb"
                total = offset
                reported = total // (32 * 1024 * 1024)
                with partial.open(mode) as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        handle.write(chunk)
                        total += len(chunk)
                        step = total // (32 * 1024 * 1024)
                        if step > reported:
                            reported = step
                            print(f"{repo}: {total / 1024**2:.0f} / {meta.size / 1024**2:.0f} MiB", flush=True)
            if partial.stat().st_size != meta.size:
                raise IOError("Incomplete model download")
            if expected_hash:
                with partial.open("rb") as handle:
                    actual = hashlib.file_digest(handle, "sha256").hexdigest()
                if actual != expected_hash:
                    partial.unlink()
                    raise IOError("Model SHA256 mismatch; retrying download")
            partial.replace(final)
            return
        except (requests.RequestException, OSError) as exc:
            if attempt == 4:
                raise
            print(f"Download interrupted ({type(exc).__name__}); resuming…", flush=True)
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--whisper", choices=["tiny", "base", "small", "medium", "large-v3-turbo"], default="small")
    parser.add_argument("--skip-tts", action="store_true", help="Download only ASR and translation files")
    args = parser.parse_args()
    print("Downloading local ASR model…", flush=True)
    whisper_repo = (f"Systran/faster-whisper-{args.whisper}" if args.whisper != "large-v3-turbo"
                    else "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
    snapshot_download(whisper_repo,
                      local_dir=ROOT / "models" / "whisper",
                      allow_patterns=["*.json", "vocabulary.*", "README.md", "LICENSE*"])
    download_weights(whisper_repo, ROOT / "models" / "whisper")
    print("Downloading MIT-licensed M2M100 translation model…", flush=True)
    snapshot_download("jncraton/m2m100_418M-ct2-int8",
                      revision="7c1b2620a4e58dacecbd8bf89cfd6da7eb9eb7b0",
                      local_dir=ROOT / "models" / "m2m100",
                      allow_patterns=["*.json", "*.txt", "README.md", "LICENSE*"])
    download_weights("jncraton/m2m100_418M-ct2-int8", ROOT / "models" / "m2m100",
                     revision="7c1b2620a4e58dacecbd8bf89cfd6da7eb9eb7b0")
    snapshot_download("facebook/m2m100_418M", revision="55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636",
                      local_dir=ROOT / "models" / "m2m100-tokenizer",
                      allow_patterns=["config.json", "generation_config.json", "tokenizer_config.json",
                                      "special_tokens_map.json", "README.md", "LICENSE*"])
    for filename in ("sentencepiece.bpe.model", "vocab.json"):
        download_weights("facebook/m2m100_418M", ROOT / "models" / "m2m100-tokenizer",
                         revision="55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636", filename=filename)
    if not args.skip_tts:
        print("Downloading MIT-licensed Chinese speech model…", flush=True)
        tts_repo = "csukuangfj/vits-melo-tts-zh_en"
        tts_revision = "a0d5c6a264c0ef92d70d8661d8cc502d79627cd6"
        snapshot_download(tts_repo, revision=tts_revision, local_dir=ROOT / "models" / "chinese-tts",
                          allow_patterns=["tokens.txt", "lexicon.txt", "*.fst", "LICENSE", "README.md"])
        download_weights(tts_repo, ROOT / "models" / "chinese-tts", revision=tts_revision, filename="model.onnx")
        print("Preparing local Japanese TTS…", flush=True)
        import pyopenjtalk
        pyopenjtalk.tts("準備ができました。")
    print("Ready. Run start.cmd. Models remain on this computer only.", flush=True)


if __name__ == "__main__":
    main()
