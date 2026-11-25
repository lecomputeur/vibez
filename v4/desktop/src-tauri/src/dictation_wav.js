// Mistral dictation uses an audio-only MediaRecorder without format options.
// On Linux, produce PCM WAV for that recorder using the already granted stream.
// The page still handles upload and transcription through its normal flow.
(() => {
  if (window !== window.top ||
      !["https://chat.mistral.ai", "https://vibe.mistral.ai"].includes(location.origin)) return;
  const NativeRecorder = window.MediaRecorder;
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!NativeRecorder || !Audio?.prototype.createScriptProcessor || !window.BlobEvent) return;

  const mimeType = "audio/wav";

  function waveHeader(sampleRate, length) {
    const header = new DataView(new ArrayBuffer(44));
    function text(offset, value) {
      for (let i = 0; i < value.length; i++) header.setUint8(offset + i, value.charCodeAt(i));
    }
    text(0, "RIFF");
    header.setUint32(4, 36 + length, true);
    text(8, "WAVE");
    text(12, "fmt ");
    header.setUint32(16, 16, true);
    header.setUint16(20, 1, true);
    header.setUint16(22, 1, true);
    header.setUint32(24, sampleRate, true);
    header.setUint32(28, sampleRate * 2, true);
    header.setUint16(32, 2, true);
    header.setUint16(34, 16, true);
    text(36, "data");
    header.setUint32(40, length, true);
    return header.buffer;
  }

  class WavRecorder extends EventTarget {
    #context;
    #source;
    #processor;
    #chunks = [];
    #length = 0;
    #stream;
    #state = "inactive";
    #onInactive = () => { if (this.state !== "inactive") this.stop(); };

    constructor(stream) {
      super();
      this.#stream = stream;
    }

    get stream() { return this.#stream; }
    get state() { return this.#state; }
    get mimeType() { return mimeType; }

    start() {
      this.#requireState("inactive");
      this.#chunks = [];
      this.#length = 0;
      try {
        const context = new Audio({ sampleRate: 16000 });
        this.#context = context;
        this.#source = context.createMediaStreamSource(this.stream);
        this.#processor = context.createScriptProcessor(1024, 1, 1);
        this.#processor.onaudioprocess = ({ inputBuffer }) => {
          if (this.state !== "recording") return;
          const samples = inputBuffer.getChannelData(0);
          const pcm = new DataView(new ArrayBuffer(samples.length * 2));
          for (let i = 0; i < samples.length; i++) {
            const sample = Math.max(-1, Math.min(1, samples[i]));
            pcm.setInt16(i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
          }
          if (this.#length + pcm.byteLength > 0xffffffff - 36) {
            this.#fail(new DOMException("The WAV recording is too large", "NotSupportedError"));
            return;
          }
          this.#chunks.push(pcm.buffer);
          this.#length += pcm.byteLength;
        };
        this.#source.connect(this.#processor);
        // The output buffer is untouched, so this connection plays silence.
        this.#processor.connect(context.destination);
        this.#state = "recording";
        this.stream.addEventListener("inactive", this.#onInactive);
        context.resume().catch(error => {
          if (this.#context === context) this.#fail(error);
        });
      } catch (error) {
        this.#release();
        throw error;
      }
    }

    pause() {
      this.#requireState("recording");
      this.#state = "paused";
    }

    resume() {
      this.#requireState("paused");
      this.#state = "recording";
    }

    stop() {
      if (this.state === "inactive") throw new DOMException("Recorder is inactive", "InvalidStateError");
      const data = this.#length
        ? new Blob([waveHeader(this.#context.sampleRate, this.#length), ...this.#chunks], { type: mimeType })
        : new Blob([], { type: mimeType });
      this.#release();
      setTimeout(() => {
        this.dispatchEvent(new BlobEvent("dataavailable", { data }));
        this.dispatchEvent(new Event("stop"));
      }, 0);
    }

    #requireState(state) {
      if (this.state !== state) throw new DOMException("Invalid recorder state", "InvalidStateError");
    }

    #fail(error) {
      this.#release();
      this.dispatchEvent(new ErrorEvent("error", { error }));
    }

    #release() {
      this.stream.removeEventListener("inactive", this.#onInactive);
      if (this.#processor) {
        this.#processor.onaudioprocess = null;
        this.#processor.disconnect();
      }
      this.#source?.disconnect();
      this.#context?.close().catch(() => {});
      this.#context = this.#processor = this.#source = undefined;
      this.#state = "inactive";
      this.#chunks = [];
      this.#length = 0;
    }
  }

  const Recorder = new Proxy(NativeRecorder, {
    construct(target, args, constructor) {
      const [stream, options] = args;
      if (constructor === Recorder && options === undefined && stream instanceof MediaStream &&
          stream.active && stream.getAudioTracks().length && !stream.getVideoTracks().length) {
        return new WavRecorder(stream);
      }
      return Reflect.construct(target, args, constructor);
    },
  });
  window.MediaRecorder = Recorder;
})();
