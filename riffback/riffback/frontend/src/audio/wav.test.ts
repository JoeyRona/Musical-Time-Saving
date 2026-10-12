import { describe, expect, it } from "vitest";
import { encodeWav, pickGuitarChannel } from "./wav";

describe("encodeWav", () => {
  it("writes a valid 16-bit PCM header", async () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1, -1, 2]);
    const view = new DataView(await encodeWav([samples], 44100).arrayBuffer());
    const text = (offset: number) => String.fromCharCode(...new Uint8Array(view.buffer, offset, 4));

    expect(text(0)).toBe("RIFF");
    expect(text(8)).toBe("WAVE");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(44100);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(samples.length * 2);
  });

  it("converts and clips samples", async () => {
    const view = new DataView(await encodeWav([new Float32Array([0.5, -1, 2])], 8000).arrayBuffer());
    expect(view.getInt16(44, true)).toBe(Math.trunc(0.5 * 0x7fff));
    expect(view.getInt16(46, true)).toBe(-0x8000);
    expect(view.getInt16(48, true)).toBe(0x7fff); // 2 is clipped to 1
  });

  it("interleaves stereo", async () => {
    const left = new Float32Array([1, 1]);
    const right = new Float32Array([-1, -1]);
    const view = new DataView(await encodeWav([left, right], 8000).arrayBuffer());
    expect(view.getUint16(22, true)).toBe(2);
    expect(view.getInt16(44, true)).toBeGreaterThan(0);
    expect(view.getInt16(46, true)).toBeLessThan(0);
  });
});

describe("pickGuitarChannel", () => {
  it("keeps the louder channel", () => {
    const guitar = new Float32Array([0.5, -0.4, 0.6]);
    const silence = new Float32Array([0.001, 0, -0.001]);
    expect(pickGuitarChannel([silence, guitar])).toBe(guitar);
    expect(pickGuitarChannel([guitar, silence])).toBe(guitar);
  });
});
