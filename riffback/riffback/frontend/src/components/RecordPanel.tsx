import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { type InputDevice, listInputs, Recorder } from "../audio/recorder";

const MAX_SECONDS = 60;
const LEDS = 12;

interface Props {
  busy: boolean;
  onRecorded: (wav: Blob) => void;
  onError: (message: string) => void;
}

export function RecordPanel({ busy, onRecorded, onError }: Props) {
  const [devices, setDevices] = useState<InputDevice[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const recorder = useRef<Recorder | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refreshDevices = async () => {
    try {
      const inputs = await listInputs();
      setDevices(inputs);
      // Prefer an audio interface over the laptop's built-in mic.
      const preferred = inputs.find((d) => /focusrite|scarlett|interface|usb audio/i.test(d.label));
      setDeviceId((current) => current || preferred?.deviceId || "");
    } catch {
      // enumerateDevices can fail on insecure origins; the default input still works.
    }
  };

  useEffect(() => {
    void refreshDevices();
    return () => recorder.current?.cancel();
  }, []);

  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => {
      const s = recorder.current?.seconds ?? 0;
      setSeconds(s);
      if (s >= MAX_SECONDS) void stop();
    }, 100);
    return () => clearInterval(id);
  });

  const start = async () => {
    const rec = new Recorder();
    rec.onLevel = (peak) => setLevel((prev) => Math.max(peak, prev * 0.85));
    try {
      await rec.start(deviceId || undefined);
    } catch (err) {
      const denied = err instanceof DOMException && err.name === "NotAllowedError";
      onError(
        denied
          ? "Microphone access is blocked. Allow it in your browser's site settings, then try again."
          : "Couldn't open that input. Check your interface is plugged in, or pick another input.",
      );
      return;
    }
    recorder.current = rec;
    setSeconds(0);
    setRecording(true);
    // Device names only appear after permission is granted.
    void refreshDevices();
  };

  const stop = async () => {
    const rec = recorder.current;
    if (!rec) return;
    recorder.current = null;
    setRecording(false);
    setLevel(0);
    const wav = await rec.stop();
    onRecorded(wav);
  };

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onRecorded(file);
  };

  const lit = Math.round(Math.min(1, level) * LEDS);
  const clipping = level > 0.98;

  return (
    <section className="panel" aria-labelledby="record-title">
      <div className="panel-head">
        <h2 id="record-title">Play your riff</h2>
        <p className="hint">
          Play it at least twice through without a click. Open chords or a slow melody work best. Stop when you're done.
        </p>
      </div>

      <div className="rig">
        <button
          type="button"
          className={`record-button${recording ? " is-recording" : ""}`}
          onClick={recording ? stop : start}
          disabled={busy}
          aria-pressed={recording}
        >
          <span className="lamp" aria-hidden="true" />
          {recording ? "Stop" : "Record"}
        </button>

        <div className="rig-controls">
          <label className="field">
            <span>Input</span>
            <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} disabled={recording || busy}>
              <option value="">Default input</option>
              {devices
                .filter((d) => d.deviceId && d.deviceId !== "default")
                .map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </option>
                ))}
            </select>
          </label>

          <div className="meter" role="meter" aria-label="Input level" aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={Math.round(level * 100)}>
            {Array.from({ length: LEDS }, (_, i) => (
              <span key={i} className={`led${i < lit ? " on" : ""}${i >= LEDS - 2 ? " hot" : ""}`} />
            ))}
            <span className="timer">{recording ? `${seconds.toFixed(1)}s` : "0.0s"}</span>
          </div>
          {clipping && <p className="warn">Clipping: turn the gain knob on your interface down a little.</p>}
        </div>
      </div>

      <p className="alt">
        Already have a recording?{" "}
        <button type="button" className="link" onClick={() => fileInput.current?.click()} disabled={busy || recording}>
          Upload a WAV file
        </button>
        <input ref={fileInput} type="file" accept=".wav,audio/wav,audio/x-wav" hidden onChange={onFile} />
      </p>
    </section>
  );
}
