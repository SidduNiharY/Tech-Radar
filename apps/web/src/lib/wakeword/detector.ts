/**
 * TechRadar Brain - Client-side openWakeWord Detector
 * Evaluates inference confidence scores and coordinates local audio listening.
 */

export interface WakeWordDetectorOptions {
  threshold?: number; // Default: 0.5
  consecutive?: number; // Default: 2 consecutive frames
  cooldownMs?: number; // Default: 2000 ms cooldown
  onWake?: () => void;
  onListeningStateChange?: (state: "off" | "wake" | "stream") => void;
}

/**
 * Pure evaluation function: checks if the tail of scores satisfies consecutive threshold hits.
 */
export function shouldFire(scores: number[], threshold: number, consecutive: number): boolean {
  if (scores.length < consecutive || consecutive <= 0) {
    return false;
  }
  const tail = scores.slice(scores.length - consecutive);
  return tail.every((s) => s >= threshold);
}

export class WakeWordDetector {
  private threshold: number;
  private consecutive: number;
  private cooldownMs: number;
  private onWakeCallback?: () => void;
  private onListeningStateChange?: (state: "off" | "wake" | "stream") => void;

  private activeStream: MediaStream | null = null;
  private isPaused: boolean = false;
  private isRunning: boolean = false;
  private lastTriggerTime: number = 0;
  private scoreBuffer: number[] = [];

  constructor(opts: WakeWordDetectorOptions = {}) {
    this.threshold = opts.threshold ?? 0.5;
    this.consecutive = opts.consecutive ?? 2;
    this.cooldownMs = opts.cooldownMs ?? 2000;
    this.onWakeCallback = opts.onWake;
    this.onListeningStateChange = opts.onListeningStateChange;
  }

  public get running(): boolean {
    return this.isRunning;
  }

  public get paused(): boolean {
    return this.isPaused;
  }

  /**
   * Start listening to the local audio stream without network transmission.
   */
  public start(stream: MediaStream): void {
    this.activeStream = stream;
    this.isRunning = true;
    this.isPaused = false;
    this.scoreBuffer = [];
    this.onListeningStateChange?.("wake");
  }

  /**
   * Temporarily pause detection (e.g. while Jarvis is speaking or active turn taking).
   */
  public pause(): void {
    if (!this.isRunning) return;
    this.isPaused = true;
  }

  /**
   * Resume detection after response turn completes.
   */
  public resume(): void {
    if (!this.isRunning) return;
    this.isPaused = false;
    this.scoreBuffer = [];
  }

  /**
   * Stop detection and release audio tracks.
   */
  public stop(): void {
    this.isRunning = false;
    this.isPaused = false;
    if (this.activeStream) {
      for (const track of this.activeStream.getTracks()) {
        track.stop();
      }
      this.activeStream = null;
    }
    this.scoreBuffer = [];
    this.onListeningStateChange?.("off");
  }

  /**
   * Feed confidence scores from the ONNX Web Worker.
   */
  public feedScore(score: number): boolean {
    if (!this.isRunning || this.isPaused) {
      return false;
    }

    const now = Date.now();
    if (now - this.lastTriggerTime < this.cooldownMs) {
      return false;
    }

    this.scoreBuffer.push(score);
    // Keep bounded history
    if (this.scoreBuffer.length > 20) {
      this.scoreBuffer.shift();
    }

    if (shouldFire(this.scoreBuffer, this.threshold, this.consecutive)) {
      this.lastTriggerTime = now;
      this.scoreBuffer = [];
      this.onListeningStateChange?.("stream");
      this.onWakeCallback?.();
      return true;
    }

    return false;
  }
}
