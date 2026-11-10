/**
 * Meeting Real-Time Audio Conferencing Client (WebRTC)
 * Provides peer-to-peer encrypted audio streaming, active speaker detection,
 * mute/unmute toggles, participant presence synchronization, and
 * live multi-party audio recording with instant local and server download.
 */

(function () {
  'use strict';

  const ICE_SERVERS = [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
    { urls: 'stun:stun2.l.google.com:19302' },
  ];

  class MeetingAudioManager {
    constructor() {
      this.meetingId = null;
      this.csrfToken = null;
      this.currentUserId = null;
      this.currentUserName = null;

      this.localStream = null;
      this.audioContext = null;
      this.analyserNode = null;
      this.recordingDestNode = null; // Mixed audio destination (local + all remote tracks)
      this.speechInterval = null;
      this.isMuted = false;
      this.isSpeaking = false;
      this.isInRoom = false;

      // Recording Engine State
      this.mediaRecorder = null;
      this.recordedChunks = [];
      this.isRecording = false;
      this.recordingStartTime = 0;
      this.recordingTimerInterval = null;
      this.lastRecordingBlobUrl = null;

      this.peerConnections = new Map(); // targetUserId -> RTCPeerConnection
      this.remoteAudioElements = new Map(); // targetUserId -> HTMLAudioElement
      this.pollInterval = null;
      this.pollFrequencyMs = 1500;

      // DOM Elements Cache
      this.dom = {};
    }

    init(config) {
      this.meetingId = config.meetingId;
      this.csrfToken = config.csrfToken;
      this.currentUserId = config.currentUserId;
      this.currentUserName = config.currentUserName;

      this.cacheDomElements();
      this.bindEvents();
    }

    cacheDomElements() {
      this.dom.container = document.getElementById('meeting-audio-panel');
      this.dom.btnJoin = document.getElementById('btn-audio-join');
      this.dom.btnLeave = document.getElementById('btn-audio-leave');
      this.dom.btnMute = document.getElementById('btn-audio-mute');
      this.dom.btnRecord = document.getElementById('btn-audio-record');
      this.dom.recordBadge = document.getElementById('audio-recording-badge');
      this.dom.recordTimer = document.getElementById('audio-recording-timer');
      this.dom.recordingPlaybackCard = document.getElementById('audio-recording-playback-card');
      this.dom.recordingAudioPlayer = document.getElementById('audio-recorded-player');
      this.dom.btnDownloadRecorded = document.getElementById('btn-download-recorded-audio');
      this.dom.btnServerDownload = document.getElementById('btn-server-download-recorded-audio');

      this.dom.statusBadge = document.getElementById('audio-status-badge');
      this.dom.audioMeter = document.getElementById('audio-level-bar');
      this.dom.participantsList = document.getElementById('audio-participants-list');
      this.dom.participantsCount = document.getElementById('audio-participants-count');
      this.dom.audioStreamsContainer = document.getElementById('audio-remote-streams');
      this.dom.errorMessage = document.getElementById('audio-error-alert');
    }

    bindEvents() {
      if (this.dom.btnJoin) {
        this.dom.btnJoin.addEventListener('click', () => this.join());
      }
      if (this.dom.btnLeave) {
        this.dom.btnLeave.addEventListener('click', () => this.leave());
      }
      if (this.dom.btnMute) {
        this.dom.btnMute.addEventListener('click', () => this.toggleMute());
      }
      if (this.dom.btnRecord) {
        this.dom.btnRecord.addEventListener('click', () => this.toggleRecording());
      }

      window.addEventListener('beforeunload', () => {
        if (this.isRecording) {
          this.stopRecording();
        }
        if (this.isInRoom) {
          this.leaveSync();
        }
      });
    }

    showError(msg) {
      if (this.dom.errorMessage) {
        this.dom.errorMessage.textContent = msg;
        this.dom.errorMessage.classList.remove('d-none');
        setTimeout(() => {
          if (this.dom.errorMessage) this.dom.errorMessage.classList.add('d-none');
        }, 6000);
      } else {
        console.error('[Audio]', msg);
      }
    }

    async join() {
      if (this.isInRoom) return;
      this.showLoading(true);

      // 1. Check browser WebRTC & getUserMedia support
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        this.showError('مرورگر شما از قابلیت گفتگوی صوتی آنلاین پشتیبانی نمی‌کند یا صفحه تحت پروتکل امن (HTTPS/Localhost) باز نشده است.');
        this.showLoading(false);
        return;
      }

      try {
        // 2. Request user microphone
        this.localStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
          video: false,
        });

        await this.setupAudioAnalysis();
        this.isMuted = false;

        // 3. Register in signaling server
        const resp = await fetch(`/meetings/${this.meetingId}/audio/join`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.csrfToken,
          },
          body: JSON.stringify({ csrf_token: this.csrfToken }),
        });

        if (!resp.ok) {
          throw new Error(`Signaling join failed: ${resp.status}`);
        }

        const data = await resp.json();
        this.isInRoom = true;
        this.showLoading(false);
        this.updateUIState(true);

        // 4. Connect to all existing participants in the room
        if (data.other_participants && data.other_participants.length > 0) {
          for (const p of data.other_participants) {
            await this.initiateCall(p.user_id);
          }
        }

        this.renderParticipants(data.all_participants || []);

        // 5. Start signal polling
        this.startPolling();
      } catch (err) {
        console.error('[Audio Join Error]', err);
        this.showLoading(false);
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          this.showError('دسترسی به میکروفون توسط کاربر یا مرورگر مسدود شده است. لطفاً اجازه دسترسی را در مرورگر فعال کنید.');
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          this.showError('هیچ میکروفونی در سیستم شناسایی نشد.');
        } else {
          this.showError(`خطا در اتصال صوتی: ${err.message || err}`);
        }
        this.cleanup();
      }
    }

    async setupAudioAnalysis() {
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        this.audioContext = new AudioCtx();
        if (this.audioContext.state === 'suspended') {
          await this.audioContext.resume();
        }

        // 1. Create source for local microphone
        const source = this.audioContext.createMediaStreamSource(this.localStream);
        this.analyserNode = this.audioContext.createAnalyser();
        this.analyserNode.fftSize = 256;
        source.connect(this.analyserNode);

        // 2. Create mixed destination for recording (combining local mic + all remote peer voices)
        this.recordingDestNode = this.audioContext.createMediaStreamDestination();
        source.connect(this.recordingDestNode);

        const dataArray = new Uint8Array(this.analyserNode.frequencyBinCount);

        this.speechInterval = setInterval(() => {
          if (!this.isInRoom || this.isMuted || !this.analyserNode) {
            this.setSpeakingState(false);
            if (this.dom.audioMeter) this.dom.audioMeter.style.width = '0%';
            return;
          }

          this.analyserNode.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
          }
          const avg = sum / dataArray.length;

          // Update audio level meter UI
          const percent = Math.min(100, Math.round((avg / 128) * 100));
          if (this.dom.audioMeter) {
            this.dom.audioMeter.style.width = `${percent}%`;
          }

          const isSpeakingNow = avg > 14;
          if (isSpeakingNow !== this.isSpeaking) {
            this.setSpeakingState(isSpeakingNow);
          }
        }, 150);
      } catch (e) {
        console.warn('AudioContext analysis not supported:', e);
      }
    }

    setSpeakingState(speaking) {
      this.isSpeaking = speaking;
      // Broadcast speaking status to signaling server
      if (this.isInRoom) {
        fetch(`/meetings/${this.meetingId}/audio/status`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.csrfToken,
          },
          body: JSON.stringify({
            csrf_token: this.csrfToken,
            is_speaking: this.isSpeaking,
          }),
        }).catch(() => {});
      }
    }

    toggleMute() {
      if (!this.localStream) return;
      const audioTracks = this.localStream.getAudioTracks();
      if (audioTracks.length === 0) return;

      this.isMuted = !this.isMuted;
      audioTracks.forEach((t) => (t.enabled = !this.isMuted));

      if (this.dom.btnMute) {
        if (this.isMuted) {
          this.dom.btnMute.classList.remove('btn-outline-primary');
          this.dom.btnMute.classList.add('btn-danger');
          this.dom.btnMute.innerHTML = '<i class="fas fa-microphone-slash me-1"></i> بی‌صدا (Muted)';
        } else {
          this.dom.btnMute.classList.remove('btn-danger');
          this.dom.btnMute.classList.add('btn-outline-primary');
          this.dom.btnMute.innerHTML = '<i class="fas fa-microphone me-1"></i> میکروفون فعال';
        }
      }

      // Notify signaling
      fetch(`/meetings/${this.meetingId}/audio/status`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken,
        },
        body: JSON.stringify({
          csrf_token: this.csrfToken,
          is_muted: this.isMuted,
        }),
      }).catch(() => {});
    }

    // =========================================================================
    // Meeting Voice Recording & Download Engine
    // =========================================================================

    toggleRecording() {
      if (this.isRecording) {
        this.stopRecording();
      } else {
        this.startRecording();
      }
    }

    async startRecording() {
      if (!window.MediaRecorder) {
        this.showError('مرورگر شما از قابلیت ضبط صوتی آنلاین پشتیبانی نمی‌کند.');
        return;
      }

      try {
        // If not in room or mic not yet acquired, request microphone on the spot
        if (!this.localStream) {
          this.localStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
            video: false,
          });
          await this.setupAudioAnalysis();
        }

        if (this.audioContext && this.audioContext.state === 'suspended') {
          await this.audioContext.resume();
        }

        // Determine stream to record
        let streamToRecord = null;
        if (this.recordingDestNode && this.recordingDestNode.stream && this.recordingDestNode.stream.getAudioTracks().length > 0) {
          streamToRecord = this.recordingDestNode.stream;
        } else if (this.localStream) {
          streamToRecord = this.localStream;
        }

        if (!streamToRecord || streamToRecord.getAudioTracks().length === 0) {
          throw new Error('جریان صوتی فعالی برای ضبط در دسترس نیست.');
        }

        // Find supported MIME type
        let selectedMimeType = '';
        const mimeTypes = [
          'audio/webm;codecs=opus',
          'audio/webm',
          'audio/ogg;codecs=opus',
          'audio/ogg',
          'audio/mp4',
          'audio/aac',
        ];
        for (const mt of mimeTypes) {
          if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(mt)) {
            selectedMimeType = mt;
            break;
          }
        }

        const options = selectedMimeType ? { mimeType: selectedMimeType } : undefined;

        this.recordedChunks = [];
        this.mediaRecorder = options ? new MediaRecorder(streamToRecord, options) : new MediaRecorder(streamToRecord);

        this.mediaRecorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) {
            this.recordedChunks.push(event.data);
          }
        };

        this.mediaRecorder.onstop = () => {
          // Allow small tick for final chunk aggregation
          setTimeout(() => this.finalizeRecordingDownload(), 100);
        };

        this.mediaRecorder.start(500); // 500ms timeslice for fast chunk emission
        this.isRecording = true;
        this.recordingStartTime = Date.now();

        // Update UI
        if (this.dom.btnRecord) {
          this.dom.btnRecord.classList.remove('btn-outline-danger');
          this.dom.btnRecord.classList.add('btn-danger', 'recording-active-btn');
          this.dom.btnRecord.innerHTML = '<i class="fas fa-stop-circle me-1"></i> توقف ضبط و دانلود';
        }

        if (this.dom.recordBadge) {
          this.dom.recordBadge.classList.remove('d-none');
        }

        if (this.dom.recordingPlaybackCard) {
          this.dom.recordingPlaybackCard.classList.add('d-none');
        }

        // Start timer
        if (this.recordingTimerInterval) clearInterval(this.recordingTimerInterval);
        this.recordingTimerInterval = setInterval(() => {
          const elapsedSec = Math.floor((Date.now() - this.recordingStartTime) / 1000);
          const mins = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
          const secs = String(elapsedSec % 60).padStart(2, '0');
          if (this.dom.recordTimer) {
            this.dom.recordTimer.textContent = `${mins}:${secs}`;
          }
        }, 1000);
      } catch (err) {
        console.error('[Recording Error]', err);
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          this.showError('اجازه دسترسی به میکروفون داده نشد. لطفاً در بالای مرورگر دسترسی میکروفون را فعال کنید.');
        } else {
          this.showError(`خطا در شروع ضبط صدا: ${err.message || err}`);
        }
      }
    }

    stopRecording() {
      if (!this.isRecording || !this.mediaRecorder) return;
      this.isRecording = false;

      if (this.recordingTimerInterval) {
        clearInterval(this.recordingTimerInterval);
        this.recordingTimerInterval = null;
      }

      try {
        if (this.mediaRecorder.state === 'recording') {
          try {
            this.mediaRecorder.requestData();
          } catch (e) {}
          this.mediaRecorder.stop();
        }
      } catch (e) {
        console.warn('Error stopping mediaRecorder:', e);
      }

      // Reset Button UI
      if (this.dom.btnRecord) {
        this.dom.btnRecord.classList.remove('btn-danger', 'recording-active-btn');
        this.dom.btnRecord.classList.add('btn-outline-danger');
        this.dom.btnRecord.innerHTML = '<i class="fas fa-record-vinyl me-1"></i> ضبط مکالمه جلسه';
      }

      if (this.dom.recordBadge) {
        this.dom.recordBadge.classList.add('d-none');
      }
    }

    async finalizeRecordingDownload() {
      if (!this.recordedChunks || this.recordedChunks.length === 0) {
        console.warn('[Audio] No audio chunks were collected.');
        return;
      }

      const mimeType = (this.mediaRecorder && this.mediaRecorder.mimeType) ? this.mediaRecorder.mimeType : 'audio/webm';
      const audioBlob = new Blob(this.recordedChunks, { type: mimeType });

      if (this.lastRecordingBlobUrl) {
        try {
          URL.revokeObjectURL(this.lastRecordingBlobUrl);
        } catch (e) {}
      }

      this.lastRecordingBlobUrl = URL.createObjectURL(audioBlob);

      const d = new Date();
      const timestampStr = `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}_${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}`;
      const ext = mimeType.includes('mp4') ? 'mp4' : (mimeType.includes('ogg') ? 'ogg' : 'webm');
      const filename = `Meeting-${this.meetingId}-${timestampStr}.${ext}`;

      // 1. Update UI card & Download Anchor directly
      if (this.dom.recordingPlaybackCard) {
        this.dom.recordingPlaybackCard.classList.remove('d-none');
      }
      if (this.dom.recordingAudioPlayer) {
        this.dom.recordingAudioPlayer.src = this.lastRecordingBlobUrl;
        this.dom.recordingAudioPlayer.load();
      }
      if (this.dom.btnDownloadRecorded) {
        this.dom.btnDownloadRecorded.href = this.lastRecordingBlobUrl;
        this.dom.btnDownloadRecorded.download = filename;
      }

      // 2. Trigger instant automatic download
      try {
        const downloadAnchor = document.createElement('a');
        downloadAnchor.style.display = 'none';
        downloadAnchor.href = this.lastRecordingBlobUrl;
        downloadAnchor.download = filename;
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        setTimeout(() => {
          if (downloadAnchor.parentNode) {
            document.body.removeChild(downloadAnchor);
          }
        }, 300);
      } catch (err) {
        console.warn('[Auto-Download Warning]', err);
      }

      // 3. Upload to server as backup archive and enable direct server download link
      try {
        const formData = new FormData();
        formData.append('audio_file', audioBlob, filename);
        formData.append('csrf_token', this.csrfToken);

        const uploadResp = await fetch(`/meetings/${this.meetingId}/audio/recordings/upload`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': this.csrfToken,
          },
          body: formData,
        });

        if (uploadResp.ok) {
          const uploadData = await uploadResp.json();
          if (uploadData.download_url && this.dom.btnServerDownload) {
            this.dom.btnServerDownload.href = uploadData.download_url;
            this.dom.btnServerDownload.download = filename;
            this.dom.btnServerDownload.classList.remove('d-none');
          }
        }
      } catch (uploadErr) {
        console.warn('[Server Upload Backup Error]', uploadErr);
      }
    }

    async initiateCall(targetUserId) {
      if (this.peerConnections.has(targetUserId)) return;

      const pc = this.createPeerConnection(targetUserId);
      this.peerConnections.set(targetUserId, pc);

      // Add local stream tracks to PC
      if (this.localStream) {
        this.localStream.getTracks().forEach((track) => {
          pc.addTrack(track, this.localStream);
        });
      }

      try {
        const offer = await pc.createOffer({
          offerToReceiveAudio: true,
          offerToReceiveVideo: false,
        });
        await pc.setLocalDescription(offer);

        await this.sendSignal(targetUserId, {
          type: 'offer',
          sdp: pc.localDescription,
        });
      } catch (err) {
        console.error(`[Call Error -> ${targetUserId}]`, err);
      }
    }

    createPeerConnection(targetUserId) {
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          this.sendSignal(targetUserId, {
            type: 'candidate',
            candidate: event.candidate,
          });
        }
      };

      pc.ontrack = (event) => {
        let audioElem = this.remoteAudioElements.get(targetUserId);
        if (!audioElem) {
          audioElem = document.createElement('audio');
          audioElem.autoplay = true;
          audioElem.id = `remote-audio-${targetUserId}`;
          if (this.dom.audioStreamsContainer) {
            this.dom.audioStreamsContainer.appendChild(audioElem);
          }
          this.remoteAudioElements.set(targetUserId, audioElem);
        }
        if (event.streams && event.streams[0]) {
          audioElem.srcObject = event.streams[0];

          // Connect incoming remote stream to the recording destination mixer
          if (this.audioContext && this.recordingDestNode) {
            try {
              const remoteSource = this.audioContext.createMediaStreamSource(event.streams[0]);
              remoteSource.connect(this.recordingDestNode);
            } catch (e) {
              console.warn('[Mixer Audio Connect Error]', e);
            }
          }
        }
      };

      pc.oniceconnectionstatechange = () => {
        if (pc.iceConnectionState === 'disconnected' || pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'closed') {
          this.closePeer(targetUserId);
        }
      };

      return pc;
    }

    async sendSignal(toUserId, signalData) {
      try {
        await fetch(`/meetings/${this.meetingId}/audio/signal`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.csrfToken,
          },
          body: JSON.stringify({
            csrf_token: this.csrfToken,
            to_user_id: toUserId,
            signal_data: signalData,
          }),
        });
      } catch (err) {
        console.warn(`[SendSignal Error -> ${toUserId}]`, err);
      }
    }

    startPolling() {
      if (this.pollInterval) clearInterval(this.pollInterval);
      this.pollInterval = setInterval(async () => {
        if (!this.isInRoom) return;
        try {
          const resp = await fetch(`/meetings/${this.meetingId}/audio/poll`);
          if (!resp.ok) return;
          const data = await resp.json();

          if (data.status === 'not_in_room') {
            // Re-sync or leave if server dropped presence
            this.leave();
            return;
          }

          if (data.participants) {
            this.renderParticipants(data.participants);
            this.syncPeerConnections(data.participants);
          }

          if (data.signals && data.signals.length > 0) {
            for (const sig of data.signals) {
              await this.handleIncomingSignal(sig);
            }
          }
        } catch (err) {
          console.warn('[Poll Error]', err);
        }
      }, this.pollFrequencyMs);
    }

    async handleIncomingSignal(signalItem) {
      const fromId = signalItem.from_user_id;
      const data = signalItem.signal_data;
      if (!data || fromId === this.currentUserId) return;

      let pc = this.peerConnections.get(fromId);

      if (data.type === 'offer') {
        if (!pc) {
          pc = this.createPeerConnection(fromId);
          this.peerConnections.set(fromId, pc);
          if (this.localStream) {
            this.localStream.getTracks().forEach((track) => {
              pc.addTrack(track, this.localStream);
            });
          }
        }
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        await this.sendSignal(fromId, {
          type: 'answer',
          sdp: pc.localDescription,
        });
      } else if (data.type === 'answer') {
        if (pc) {
          await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
        }
      } else if (data.type === 'candidate') {
        if (pc && data.candidate) {
          try {
            await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
          } catch (e) {
            console.warn('[AddCandidate Error]', e);
          }
        }
      }
    }

    syncPeerConnections(activeParticipants) {
      const activeUserIds = new Set(activeParticipants.map((p) => p.user_id));
      for (const [userId, pc] of this.peerConnections.entries()) {
        if (!activeUserIds.has(userId)) {
          this.closePeer(userId);
        }
      }
    }

    closePeer(userId) {
      const pc = this.peerConnections.get(userId);
      if (pc) {
        pc.close();
        this.peerConnections.delete(userId);
      }
      const audioElem = this.remoteAudioElements.get(userId);
      if (audioElem) {
        audioElem.srcObject = null;
        if (audioElem.parentNode) audioElem.parentNode.removeChild(audioElem);
        this.remoteAudioElements.delete(userId);
      }
    }

    leave() {
      if (this.isRecording) {
        this.stopRecording();
      }

      if (!this.isInRoom) return;
      this.isInRoom = false;

      fetch(`/meetings/${this.meetingId}/audio/leave`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken,
        },
        body: JSON.stringify({ csrf_token: this.csrfToken }),
      }).catch(() => {});

      this.cleanup();
      this.updateUIState(false);
      this.renderParticipants([]);
    }

    leaveSync() {
      try {
        const payload = JSON.stringify({ csrf_token: this.csrfToken });
        navigator.sendBeacon(`/meetings/${this.meetingId}/audio/leave`, payload);
      } catch (e) {}
    }

    cleanup() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
      if (this.speechInterval) {
        clearInterval(this.speechInterval);
        this.speechInterval = null;
      }
      if (this.audioContext) {
        try {
          this.audioContext.close();
        } catch (e) {}
        this.audioContext = null;
      }
      if (this.localStream) {
        this.localStream.getTracks().forEach((track) => track.stop());
        this.localStream = null;
      }

      for (const [uid] of this.peerConnections.entries()) {
        this.closePeer(uid);
      }

      if (this.dom.audioMeter) this.dom.audioMeter.style.width = '0%';
    }

    showLoading(loading) {
      if (this.dom.btnJoin) {
        this.dom.btnJoin.disabled = loading;
        this.dom.btnJoin.innerHTML = loading
          ? '<i class="fas fa-spinner fa-spin me-1"></i> در حال اتصال...'
          : '<i class="fas fa-headphones-alt me-1"></i> ورود به گفتگوی صوتی جلسه';
      }
    }

    updateUIState(inRoom) {
      if (this.dom.btnJoin) this.dom.btnJoin.classList.toggle('d-none', inRoom);
      if (this.dom.btnLeave) this.dom.btnLeave.classList.toggle('d-none', !inRoom);
      if (this.dom.btnMute) this.dom.btnMute.classList.toggle('d-none', !inRoom);

      if (this.dom.statusBadge) {
        if (inRoom) {
          this.dom.statusBadge.className = 'badge bg-success-subtle text-success px-3 py-2';
          this.dom.statusBadge.innerHTML = '<i class="fas fa-circle text-success pulse-dot me-1"></i> آنلاین در اتاق صوتی';
        } else {
          this.dom.statusBadge.className = 'badge bg-secondary-subtle text-secondary px-3 py-2';
          this.dom.statusBadge.innerHTML = '<i class="fas fa-circle-notch me-1"></i> آفلاین';
        }
      }
    }

    renderParticipants(participants) {
      if (this.dom.participantsCount) {
        this.dom.participantsCount.textContent = participants.length;
      }
      if (!this.dom.participantsList) return;

      if (!participants || participants.length === 0) {
        this.dom.participantsList.innerHTML = `
          <div class="text-muted small text-center py-2">
            <i class="fas fa-user-friends me-1"></i> هنوز کاربری وارد اتاق صوتی نشده است.
          </div>
        `;
        return;
      }

      const html = participants
        .map((p) => {
          const isSelf = p.user_id === this.currentUserId;
          const speakingClass = p.is_speaking ? 'participant-speaking-pulse' : '';
          const muteBadge = p.is_muted
            ? '<span class="badge bg-danger-subtle text-danger ms-2"><i class="fas fa-microphone-slash"></i> بی‌صدا</span>'
            : '<span class="badge bg-success-subtle text-success ms-2"><i class="fas fa-microphone"></i> فعال</span>';

          const roleLabel = p.role === 'admin' ? 'مدیر ارشد' : p.role === 'manager' ? 'مدیر' : 'عضو';

          return `
          <div class="audio-participant-chip ${speakingClass} ${isSelf ? 'chip-self' : ''}">
            <div class="audio-avatar">
              <i class="fas fa-user"></i>
            </div>
            <div class="audio-participant-info">
              <span class="audio-participant-name">${p.user_name} ${isSelf ? '(شما)' : ''}</span>
              <span class="audio-participant-role">${roleLabel}</span>
            </div>
            ${muteBadge}
          </div>
        `;
        })
        .join('');

      this.dom.participantsList.innerHTML = html;
    }
  }

  window.MeetingAudioManager = new MeetingAudioManager();
})();
