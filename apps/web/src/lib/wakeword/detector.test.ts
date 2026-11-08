import { describe, expect, it } from "vitest";
import { WakeWordDetector, shouldFire } from "./detector";
import { FRAME_DURATION_MS, SAMPLES_PER_FRAME, TARGET_SAMPLE_RATE, framesFrom } from "./frames";

describe("openWakeWord Scoring & Frame Tests", () => {
  it("fires only on consecutive frames over threshold", () => {
    expect(shouldFire([0.6, 0.4, 0.7], 0.5, 2)).toBe(false);
    expect(shouldFire([0.6, 0.7], 0.5, 2)).toBe(true);
    expect(shouldFire([0.4, 0.6, 0.8], 0.5, 2)).toBe(true);
    expect(shouldFire([0.6, 0.8, 0.4], 0.5, 2)).toBe(false);
  });

  it("handles edge cases for shouldFire", () => {
    expect(shouldFire([], 0.5, 2)).toBe(false);
    expect(shouldFire([0.9], 0.5, 2)).toBe(false);
    expect(shouldFire([0.9], 0.5, 0)).toBe(false);
  });

  it("slices audio samples into 16 kHz 80 ms Int16 frames", () => {
    // 1 frame = 1280 samples at 16 kHz
    expect(SAMPLES_PER_FRAME).toBe(1280);
    expect(TARGET_SAMPLE_RATE).toBe(16000);
    expect(FRAME_DURATION_MS).toBe(80);

    const samples = new Float32Array(2560); // 2 full frames
    samples.fill(0.5);
    const frames = framesFrom(samples, 16000);

    expect(frames.length).toBe(2);
    expect(frames[0].length).toBe(1280);
    expect(frames[1].length).toBe(1280);
    // 0.5 in float32 scaled to Int16 is ~16383
    expect(frames[0][0]).toBeGreaterThan(16000);
  });

  it("resamples 48 kHz audio to 16 kHz correctly", () => {
    // 48 kHz audio has 3x samples for same duration.
    // 1 frame at 16 kHz (1280 samples) needs 3840 samples at 48 kHz.
    const samples48k = new Float32Array(3840);
    samples48k.fill(0.25);
    const frames = framesFrom(samples48k, 48000);

    expect(frames.length).toBe(1);
    expect(frames[0].length).toBe(1280);
    expect(frames[0][0]).toBeGreaterThan(8000);
  });

  it("returns empty array for empty audio input", () => {
    expect(framesFrom(new Float32Array(0), 16000)).toEqual([]);
  });

  it("coordinates lifecycle and triggers onWake upon consecutive hits", () => {
    let wokeCount = 0;
    let state = "off";

    const detector = new WakeWordDetector({
      threshold: 0.5,
      consecutive: 2,
      cooldownMs: 100,
      onWake: () => {
        wokeCount++;
      },
      onListeningStateChange: (s) => {
        state = s;
      },
    });

    // Mock MediaStream
    const mockTrack = { stop: () => {} };
    const mockStream = {
      getTracks: () => [mockTrack],
    } as unknown as MediaStream;

    detector.start(mockStream);
    expect(detector.running).toBe(true);
    expect(state).toBe("wake");

    // Feed sub-threshold score
    expect(detector.feedScore(0.3)).toBe(false);
    expect(wokeCount).toBe(0);

    // Feed one over-threshold score
    expect(detector.feedScore(0.7)).toBe(false);
    expect(wokeCount).toBe(0);

    // Feed second consecutive over-threshold score -> should fire!
    expect(detector.feedScore(0.8)).toBe(true);
    expect(wokeCount).toBe(1);
    expect(state).toBe("stream");

    // Pause prevents firing
    detector.pause();
    expect(detector.paused).toBe(true);
    expect(detector.feedScore(0.9)).toBe(false);

    detector.resume();
    expect(detector.paused).toBe(false);

    // Stop shuts down and resets state
    detector.stop();
    expect(detector.running).toBe(false);
    expect(state).toBe("off");
  });
});
