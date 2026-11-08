/**
 * TechRadar Brain - Audio Frame Processor for openWakeWord
 * Converts raw audio samples into 16 kHz, 80 ms Int16 frames (1,280 samples/frame).
 */

export const TARGET_SAMPLE_RATE = 16000;
export const FRAME_DURATION_MS = 80;
export const SAMPLES_PER_FRAME = Math.round((TARGET_SAMPLE_RATE * FRAME_DURATION_MS) / 1000); // 1,280

/**
 * Resample float32 audio to 16 kHz and convert into 80 ms Int16Array frames.
 */
export function framesFrom(samples: Float32Array, rate: number): Int16Array[] {
  if (!samples || samples.length === 0) {
    return [];
  }

  // Resample to TARGET_SAMPLE_RATE (16 kHz)
  let resampled: Float32Array;
  if (rate === TARGET_SAMPLE_RATE) {
    resampled = samples;
  } else {
    const ratio = TARGET_SAMPLE_RATE / rate;
    const targetLength = Math.floor(samples.length * ratio);
    resampled = new Float32Array(targetLength);
    for (let i = 0; i < targetLength; i++) {
      const srcIndex = i / ratio;
      const index0 = Math.floor(srcIndex);
      const index1 = Math.min(index0 + 1, samples.length - 1);
      const frac = srcIndex - index0;
      resampled[i] = (1 - frac) * samples[index0] + frac * samples[index1];
    }
  }

  // Chunk into 80 ms (1,280 samples) Int16 frames
  const frameCount = Math.floor(resampled.length / SAMPLES_PER_FRAME);
  const frames: Int16Array[] = [];

  for (let f = 0; f < frameCount; f++) {
    const frame = new Int16Array(SAMPLES_PER_FRAME);
    const offset = f * SAMPLES_PER_FRAME;
    for (let i = 0; i < SAMPLES_PER_FRAME; i++) {
      const s = Math.max(-1.0, Math.min(1.0, resampled[offset + i]));
      // Scale to 16-bit integer range [-32768, 32767]
      frame[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
    }
    frames.push(frame);
  }

  return frames;
}
