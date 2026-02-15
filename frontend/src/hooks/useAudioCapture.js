import { useState, useRef, useCallback } from 'react';

const TARGET_SAMPLE_RATE = 16000;

const workletCode = `
class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 2048;
    this._buffer = new Float32Array(this.bufferSize);
    this._bytesWritten = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channelData = input[0];
    if (!channelData || channelData.length === 0) return true;

    for (let i = 0; i < channelData.length; i++) {
      this._buffer[this._bytesWritten++] = channelData[i];
      if (this._bytesWritten >= this.bufferSize) {
        this.port.postMessage(this._buffer.slice(0, this.bufferSize));
        this._bytesWritten = 0;
      }
    }
    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor);
`;

function downsampleBuffer(input, inputSampleRate, outputSampleRate) {
  if (inputSampleRate <= outputSampleRate) {
    return input;
  }

  const sampleRateRatio = inputSampleRate / outputSampleRate;
  const outputLength = Math.round(input.length / sampleRateRatio);
  const output = new Float32Array(outputLength);

  let outputOffset = 0;
  let inputOffset = 0;
  while (outputOffset < output.length) {
    const nextInputOffset = Math.round((outputOffset + 1) * sampleRateRatio);
    let accum = 0;
    let count = 0;
    for (let i = inputOffset; i < nextInputOffset && i < input.length; i++) {
      accum += input[i];
      count++;
    }
    output[outputOffset] = count > 0 ? accum / count : 0;
    outputOffset++;
    inputOffset = nextInputOffset;
  }

  return output;
}

function calculateAdaptiveGain(floatData) {
  let peak = 0;
  for (let i = 0; i < floatData.length; i++) {
    const abs = Math.abs(floatData[i]);
    if (abs > peak) peak = abs;
  }

  if (peak < 0.001) return 1;

  const targetPeak = 0.08;
  const gain = targetPeak / peak;
  return Math.max(1, Math.min(12, gain));
}

export function useAudioCapture() {
  const [isRecording, setIsRecording] = useState(false);
  const audioContextRef = useRef(null);
  const streamRef = useRef(null);
  const sourceRef = useRef(null);
  const workletNodeRef = useRef(null);

  const startCapture = useCallback(async (onAudioData, options = {}) => {
    const outputMode = options.output === 'arraybuffer' ? 'arraybuffer' : 'base64';
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1,
        }
      });

      streamRef.current = stream;

      const audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: TARGET_SAMPLE_RATE,
      });
      audioContextRef.current = audioContext;

      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const blob = new Blob([workletCode], { type: 'application/javascript' });
      const workletUrl = URL.createObjectURL(blob);
      await audioContext.audioWorklet.addModule(workletUrl);

      const workletNode = new AudioWorkletNode(audioContext, 'audio-processor');
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (event) => {
        const float32Data = event.data;
        const normalizedData = downsampleBuffer(
          float32Data,
          audioContext.sampleRate,
          TARGET_SAMPLE_RATE
        );

        const adaptiveGain = calculateAdaptiveGain(normalizedData);

        const int16Data = new Int16Array(normalizedData.length);
        for (let i = 0; i < normalizedData.length; i++) {
          const sample = Math.max(-1, Math.min(1, normalizedData[i] * adaptiveGain));
          int16Data[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        }

        if (outputMode === 'arraybuffer') {
          onAudioData(int16Data.buffer.slice(0));
          return;
        }

        const bytes = new Uint8Array(int16Data.buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        onAudioData(window.btoa(binary));
      };

      // Keep graph alive but silent.
      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      source.connect(workletNode);
      workletNode.connect(silentGain);
      silentGain.connect(audioContext.destination);

      setIsRecording(true);
      return true;
    } catch (error) {
      console.error('Error starting audio capture:', error);
      return false;
    }
  }, []);

  const stopCapture = useCallback(() => {
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setIsRecording(false);
  }, []);

  return {
    isRecording,
    startCapture,
    stopCapture,
    sampleRate: TARGET_SAMPLE_RATE
  };
}
