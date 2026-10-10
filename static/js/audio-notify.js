/**
 * QLNH Audio Notification System
 * Hybrid Audio: Plays real WAV audio files with Web Audio API synthesizer fallback.
 */
(() => {
  const STORAGE_KEY = "qlnh_audio_enabled";
  let isEnabled = localStorage.getItem(STORAGE_KEY) !== "false"; // Mặc định: Bật
  let audioCtx = null;
  let audioUnlocked = false;

  // Đường dẫn các file âm thanh chuẩn
  const audioFiles = {
    order: "/static/audio/order.wav",
    call: "/static/audio/call.wav",
    service: "/static/audio/call.wav",
    payment: "/static/audio/payment.wav",
    test: "/static/audio/order.wav",
    ready: "/static/audio/order.wav",
  };

  // Khởi tạo AudioContext
  const getAudioContext = () => {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
      }
    }
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume().then(() => {
        audioUnlocked = true;
      }).catch(() => {});
    } else if (audioCtx && audioCtx.state === "running") {
      audioUnlocked = true;
    }
    return audioCtx;
  };

  // Mở khóa âm thanh trên mọi thao tác người dùng
  const unlockAudio = () => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === "suspended") {
      ctx.resume().then(() => {
        audioUnlocked = true;
      }).catch(() => {});
    }
    // Kích hoạt nhẹ HTML5 Audio bằng âm vô thanh để vượt qua chính sách Autoplay
    try {
      const silent = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==");
      silent.play().catch(() => {});
    } catch (_) {}
  };

  ["click", "touchstart", "keydown", "pointerdown"].forEach((evt) => {
    document.addEventListener(evt, unlockAudio, { passive: true });
  });

  // Phát âm thanh tổng hợp dự phòng (nếu file wav bị chặn hoặc lỗi)
  const synthFallback = (frequencies = [659.25, 880.00]) => {
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      if (ctx.state === "suspended") {
        ctx.resume();
      }
      const now = ctx.currentTime;
      frequencies.forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const start = now + (idx * 0.14);
        const end = start + 0.5;

        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, start);

        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.75, start + 0.02);
        gain.gain.linearRampToValueAtTime(0.001, end);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(start);
        osc.stop(end + 0.05);
      });
    } catch (e) {
      console.warn("[QLNH Audio] Synth fallback error:", e);
    }
  };

  /**
   * Phát âm thanh chuông thông báo
   * @param {string} type - 'order' | 'call' | 'payment' | 'test'
   * @param {boolean} force - Bỏ qua cờ isEnabled (dùng khi bấm nút Thử chuông)
   */
  const playSound = (type = "order", force = false) => {
    if (!isEnabled && !force) return;

    const soundUrl = audioFiles[type] || audioFiles.order;
    try {
      const audio = new Audio(soundUrl);
      audio.volume = 0.9;
      const playPromise = audio.play();

      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          console.warn("[QLNH Audio] HTML5 Audio play error, chuyển sang Web Audio API:", err);
          synthFallback(type === "payment" ? [523.25, 659.25, 783.99] : [659.25, 880.00]);
        });
      }
    } catch (err) {
      console.warn("[QLNH Audio] Lỗi khởi tạo Audio, dùng synth:", err);
      synthFallback(type === "payment" ? [523.25, 659.25, 783.99] : [659.25, 880.00]);
    }
  };

  /**
   * Hiển thị Toast thông báo nổi trên góc màn hình
   */
  const showToast = (message, icon = "🔔", tone = "primary") => {
    let container = document.getElementById("qlnh-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "qlnh-toast-container";
      container.className = "qlnh-toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `qlnh-toast qlnh-toast-${tone}`;
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-text">${message}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add("is-visible");
    });

    window.setTimeout(() => {
      toast.classList.remove("is-visible");
      window.setTimeout(() => toast.remove(), 260);
    }, 4500);
  };

  /**
   * Cập nhật giao diện của các nút bật/tắt âm thanh
   */
  const updateButtons = () => {
    document.querySelectorAll("[data-audio-toggle]").forEach((btn) => {
      btn.setAttribute("aria-pressed", String(isEnabled));
      btn.classList.toggle("is-active", isEnabled);
      btn.classList.toggle("is-muted", !isEnabled);
      const icon = btn.querySelector(".audio-icon");
      const label = btn.querySelector(".audio-label");
      if (icon) icon.textContent = isEnabled ? "🔊" : "🔇";
      if (label) label.textContent = isEnabled ? "Chuông: Bật" : "Chuông: Tắt";
    });
  };

  /**
   * Đảo trạng thái bật/tắt
   */
  const toggleAudio = () => {
    isEnabled = !isEnabled;
    localStorage.setItem(STORAGE_KEY, String(isEnabled));
    updateButtons();
    if (isEnabled) {
      playSound("test", true);
      showToast("Đã bật âm thanh thông báo", "🔊", "success");
    } else {
      showToast("Đã tắt âm thanh thông báo", "🔇", "info");
    }
  };

  /**
   * Bấm nút thử chuông (luôn luôn phát âm thanh)
   */
  const testAudio = () => {
    // Nếu đang tắt thì tự bật lên luôn
    if (!isEnabled) {
      isEnabled = true;
      localStorage.setItem(STORAGE_KEY, "true");
      updateButtons();
    }
    unlockAudio();
    playSound("test", true);
    showToast("Đang phát thử chuông thông báo!", "🔔", "primary");
  };

  // Khởi tạo và gắn sự kiện
  document.addEventListener("DOMContentLoaded", () => {
    updateButtons();

    document.querySelectorAll("[data-audio-toggle]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        toggleAudio();
      });
    });

    document.querySelectorAll("[data-audio-test]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        testAudio();
      });
    });
  });

  // Xuất API toàn cục để có thể gọi từ console hoặc sự kiện khác
  window.QLNHAudio = {
    play: playSound,
    test: testAudio,
    toast: showToast,
    toggle: toggleAudio,
    isEnabled: () => isEnabled,
  };
})();
