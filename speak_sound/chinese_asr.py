"""Optional Apache-2.0 Chinese ASR, using the existing sherpa-onnx runtime."""
ZH_ASR_REPO = 'csukuangfj/sherpa-onnx-zipformer-ctc-zh-int8-2025-07-03'
ZH_ASR_REVISION = '824c678e9b80f301110e3ea8cee9819a7994c049'
ZH_ASR_SHA256 = 'e291b9c468b651e2697caa09bc684326c3addc6a019e78eb537cfd1a8248ca07'


def available(folder):
    return (folder / 'model.int8.onnx').is_file() and (folder / 'tokens.txt').is_file()


class ChineseRecognizer:
    def __init__(self, folder, threads):
        import sherpa_onnx
        self.engine = sherpa_onnx.OfflineRecognizer.from_zipformer_ctc(
            model=str(folder / 'model.int8.onnx'), tokens=str(folder / 'tokens.txt'),
            num_threads=min(4, max(1, threads)), provider='cpu')

    def recognize(self, samples):
        stream = self.engine.create_stream()
        stream.accept_waveform(16000, samples)
        self.engine.decode_stream(stream)
        return stream.result.text.strip()
