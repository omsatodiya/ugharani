// Turns the microphone into what Gnani's live STT wants: 16 kHz mono PCM16, 512 samples per frame.
// Runs on the audio thread; posts each 1024-byte frame to the page, which sends it to the server.

const OUT_RATE = 16000;
const FRAME = 512;

class MicCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / OUT_RATE; // input samples per output sample (3 at 48 kHz)
    this.acc = 0;
    this.count = 0;
    this.t = 0;
    this.frame = new Int16Array(FRAME);
    this.n = 0;
    this.muted = false;
    this.port.onmessage = (e) => { this.muted = !!e.data.muted; };
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      // Average each group of input samples: a cheap low-pass before dropping the rate.
      this.acc += input[i];
      this.count++;
      this.t += 1;
      if (this.t >= this.step) {
        this.t -= this.step;
        const s = this.muted ? 0 : Math.max(-1, Math.min(1, this.acc / this.count));
        this.acc = 0;
        this.count = 0;
        this.frame[this.n++] = s * 0x7fff;
        if (this.n === FRAME) {
          this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
          this.frame = new Int16Array(FRAME);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-capture", MicCapture);
