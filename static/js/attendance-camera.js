(() => {
  'use strict';
  const clock = document.querySelector('[data-clock]');
  if (clock) {
    const tick = () => { clock.textContent = new Intl.DateTimeFormat('vi-VN', {timeZone:'Asia/Ho_Chi_Minh', hour:'2-digit', minute:'2-digit', second:'2-digit'}).format(new Date()); };
    tick(); setInterval(tick, 1000);
  }
  const root = document.querySelector('[data-face-kiosk], [data-face-enrollment]');
  if (!root) return;
  const video = root.querySelector('video');
  const status = root.querySelector('.wf-camera-status');
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const enrollment = root.hasAttribute('data-face-enrollment');
  let stream = null, busy = false, sequence = 0, frames = [];
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const say = (message, kind = '') => {
    status.textContent = message; status.className = `wf-camera-status ${kind}`;
    const notice=root.querySelector('[data-camera-notice]');if(notice){notice.textContent=message;notice.hidden=false;notice.className=`wf-camera-notice ${kind}`;}
    const card=root.querySelector('[data-result-card]');
    if(card){const state=kind==='wf-success'?'success':kind==='wf-error'?'error':busy?'loading':'idle';card.dataset.state=state;root.querySelector('[data-result-symbol]').textContent={success:'✓',error:'!',loading:'…',idle:'○'}[state];}
  };
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || decodeURIComponent(document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.slice(10) || '');
  const post = async (url, body) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json', 'X-CSRFToken':csrf()}, body:JSON.stringify(body), signal:controller.signal});
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Phiên làm việc hết hạn hoặc máy chủ chưa sẵn sàng. Tải lại trang và kiểm tra với quản lý.');
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'Chưa xử lý được yêu cầu.');
      return result;
    } catch (error) {
      if (error.name === 'AbortError' || error instanceof TypeError) throw new Error('Mất kết nối hoặc quá thời gian. Kết quả có thể đã ghi; kiểm tra bảng công trước khi thử lại.');
      throw error;
    } finally { clearTimeout(timer); }
  };
  const stop = () => { stream?.getTracks().forEach(track => track.stop()); stream = null; video.srcObject = null;
    const placeholder=root.querySelector('[data-camera-placeholder]');if(placeholder)placeholder.hidden=false;
    const live=root.querySelector('[data-camera-state]');if(live){live.textContent='CAMERA CHƯA BẬT';live.classList.remove('is-active');}
  };
  const start = async () => {
    if (stream?.active) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Camera cần HTTPS hoặc localhost. Hãy mở máy bằng địa chỉ phù hợp.');
    try {
      stream = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640}, height:{ideal:480}, facingMode:'user'}, audio:false});
      video.srcObject = stream;
      await video.play();
      const placeholder=root.querySelector('[data-camera-placeholder]');if(placeholder)placeholder.hidden=true;
      const live=root.querySelector('[data-camera-state]');if(live){live.textContent='CAMERA TRỰC TIẾP';live.classList.add('is-active');}
      if (!video.videoWidth) await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Camera chưa có hình ảnh.')), 10000);
        video.addEventListener('loadeddata', () => { clearTimeout(timer); resolve(); }, {once:true});
      });
    } catch (error) { stop(); throw new Error(error.name === 'NotAllowedError' ? 'Camera chưa được cho phép. Hãy cấp quyền camera cho trang này.' : 'Không mở được camera. Kiểm tra kết nối và đóng ứng dụng đang dùng camera.'); }
  };
  const capture = () => {
    if (!video.videoWidth || video.readyState < 2) throw new Error('Camera chưa sẵn sàng.');
    const scale = Math.min(1, 960 / video.videoWidth, 720 / video.videoHeight);
    canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', .88);
  };
  window.addEventListener('pagehide', () => { sequence++; frames = []; stop(); });
  if (enrollment) {
    const cameraButton = root.querySelector('[data-camera-start]');
    const captureButton = root.querySelector('[data-capture]');
    const saveButton = root.querySelector('[data-save]');
    const resetButton = root.querySelector('[data-reset]');
    cameraButton.addEventListener('click', async () => {
      cameraButton.disabled = true;
      try { await start(); captureButton.disabled = false; say('Nhìn thẳng và chụp mẫu đầu tiên.'); }
      catch (error) { say(error.message, 'wf-error'); cameraButton.disabled = false; }
    });
    captureButton.addEventListener('click', () => {
      try {
        frames.push(capture()); captureButton.disabled = true;
        const hints = ['Quay nhẹ sang trái rồi chụp mẫu tiếp theo.', 'Quay nhẹ sang phải rồi chụp mẫu cuối.', 'Đã chụp đủ 3 mẫu. Xác nhận đồng ý rồi lưu.'];
        say(hints[frames.length-1]);
        captureButton.textContent = frames.length < 3 ? `Chụp mẫu ${frames.length+1}/3` : 'Đã chụp 3/3';
        saveButton.disabled = frames.length !== 3;
        if (frames.length < 3) setTimeout(() => { if (!busy && frames.length < 3) captureButton.disabled = false; }, 1000);
      } catch (error) { say(error.message, 'wf-error'); }
    });
    resetButton.addEventListener('click', () => { if (busy) return; frames=[]; captureButton.textContent='Chụp mẫu 1/3'; captureButton.disabled=!stream?.active; saveButton.disabled=true; say('Bắt đầu lại với 3 mẫu mới.'); });
    saveButton.addEventListener('click', async () => {
      if (busy) return;
      if (!root.querySelector('#face-consent').checked) { say('Cần xác nhận nhân viên đồng ý trước khi lưu.', 'wf-error'); return; }
      busy=true; saveButton.disabled=true; resetButton.disabled=true;
      try { const result = await post(root.dataset.saveUrl, {frames, consent:true}); say(result.message, 'wf-success'); frames=[]; stop(); cameraButton.disabled=false; captureButton.disabled=true; captureButton.textContent='Chụp mẫu 1/3'; }
      catch (error) { say(error.message, 'wf-error'); saveButton.disabled=false; }
      finally { busy=false; resetButton.disabled=false; }
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden && !busy) { stop(); captureButton.disabled=true; cameraButton.disabled=false; } });
    return;
  }
  const buttons = [...root.querySelectorAll('[data-clock-action]')];
  const cancel = root.querySelector('[data-cancel]');
  const person = root.querySelector('[data-person]');
  const pose = root.querySelector('[data-pose]');
  const progress = root.querySelector('progress');
  const identity = root.querySelector('[data-identity]');
  const stage = root.querySelector('[data-stage]');
  const shift = root.querySelector('[data-shift]');
  const movement = root.querySelector('[data-movement]');
  const movementPanel = root.querySelector('[data-movement-panel]');
  const poses = {CENTER:'Nhìn thẳng vào camera', LEFT:'Quay nhẹ mặt sang phải của bạn', RIGHT:'Quay nhẹ mặt sang trái của bạn'};
  const controls = active => { busy=active; buttons.forEach(button => {button.disabled=active;}); cancel.hidden=!active; };
  const steps = ['Bước 1/3 · Nhận diện và kiểm tra ca', 'Bước 2/3 · Quay đầu theo hướng dẫn', 'Bước 3/3 · Nhìn thẳng lại camera'];
  const setText=(selector,text)=>{const node=root.querySelector(selector);if(node)node.textContent=text;};
  const score=value=>typeof value==='number'?value.toLocaleString('vi-VN',{minimumFractionDigits:3,maximumFractionDigits:3}):'—';
  const config=JSON.parse(document.querySelector('#attendance-config')?.textContent||'{}');
  const showResult=()=>{if(window.matchMedia('(max-width:991px)').matches)root.querySelector('[data-result-card]')?.scrollIntoView({block:'center',behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});};
  setText('[data-match-threshold]',score(config.threshold));
  const feedback = result => {
    if (result.name) person.textContent=result.name;
    if (identity) {
      identity.textContent = result.recorded === true ? 'Đã ghi công thành công' : result.identified ? 'Đã nhận diện khuôn mặt · chưa ghi công' : 'Đang tìm khuôn mặt đã đăng ký';
      identity.className = `wf-identity ${result.recorded === true ? 'wf-success' : ''}`;
    }
    if (result.instruction) pose.textContent=result.instruction;
    else if (result.pose) pose.textContent=poses[result.pose];
    if (Number.isInteger(result.step)) {
      progress.value=result.step;
      if (stage) stage.textContent=steps[result.step] || '';
    }
    if (movement) movement.value=result.movement || 0;
    if (movementPanel) movementPanel.hidden=result.pose==='CENTER' || !result.pose;
    if (shift && result.shift) shift.textContent=`Ca làm: ${result.shift}`;
    if(result.employee_code)setText('[data-match-code]',result.employee_code);
    setText('[data-match-score]',score(result.similarity));
    if(result.action==='IN'||result.action==='OUT')setText('[data-action-label]',result.action==='IN'?'Vào ca':'Ra ca');
    setText('[data-record-state]',result.recorded===true?'Đã ghi công thành công':result.identified?'Đã nhận diện · chưa ghi công':'Chưa ghi nhận công');
    if(result.recorded_at)setText('[data-record-time]',new Date(result.recorded_at).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}));
  };
  const reset = () => {
    sequence++; stop(); controls(false); progress.value=0; person.textContent='Chấm công bằng khuôn mặt'; pose.textContent=poses.CENTER;
    if(identity){identity.textContent='Chưa ghi nhận công';identity.className='wf-identity';}
    if(stage)stage.textContent='1. Nhận diện và kiểm tra ca → 2. Quay đầu → 3. Nhìn lại camera';
    if(shift)shift.textContent='';
    if(movementPanel)movementPanel.hidden=true;
    setText('[data-match-code]','—');setText('[data-match-score]','—');setText('[data-record-time]','—');
    setText('[data-action-label]','Tự xác định');setText('[data-record-state]','Chưa ghi nhận công');
  };
  cancel.addEventListener('click', () => {reset(); say('Đã dừng. Bấm Chấm công để bắt đầu lượt mới. Nếu vừa gửi xác nhận, kiểm tra bảng công trước khi thử lại.');});
  document.addEventListener('visibilitychange', () => { if (document.hidden) { reset(); say('Đã dừng camera. Kiểm tra bảng công nếu lượt xác nhận đang được gửi.'); } });
  buttons.forEach(button => button.addEventListener('click', async () => {
    if (busy) return;
    reset();const current = ++sequence;
    controls(true); progress.value=0; person.textContent='Đang xác minh khuôn mặt';
    if(identity)identity.textContent='Chưa ghi nhận công';
    if(shift)shift.textContent='';
    try {
      await start();
      if (current !== sequence) { stop(); return; }
      say('Đang chuẩn bị lượt xác minh…');
      let result = await post(root.dataset.apiUrl, {operation:'start', action:button.dataset.clockAction});
      if(current!==sequence)return;
      const id = result.id;
      feedback(result);
      for (let attempt=0; attempt<24 && current===sequence; attempt++) {
        await sleep(1200);
        if (current !== sequence) return;
        const next = await post(root.dataset.apiUrl, {operation:'frame', id, frame:capture()});
        if (current !== sequence) return;
        feedback(next);
        if (next.done) {
          const recorded=next.recorded === true;
          progress.value=recorded ? 3 : (next.step || 0);
          say(next.message + (next.shift ? ` ${next.shift}.` : ''), recorded ? 'wf-success' : 'wf-error');
          pose.textContent=recorded ? 'Cảm ơn bạn!' : 'Chưa ghi công — xem lý do ở trên';
          if(stage)stage.textContent=recorded ? 'Hoàn tất · giờ công đã được lưu' : 'Dừng chấm công · không có bản ghi mới';
          if(movementPanel)movementPanel.hidden=true;
          stop(); controls(false);
          showResult();
          const finished = sequence;
          if(recorded) setTimeout(() => { if (sequence===finished && !busy) { reset(); say('Sẵn sàng cho nhân viên tiếp theo.'); } }, 10000);
          return;
        }
        result=next;
        if (next.ok) say('Đã nhận diện và tìm thấy ca làm. Hoàn tất động tác để ghi công.');
        else say(next.message, next.code==='pose_mismatch' ? '' : 'wf-error');
      }
      if (current===sequence) {
        say(result.identified ? 'Đã nhận diện nhưng chưa hoàn tất động tác, công chưa được ghi. Hãy thử lại và làm theo hướng dẫn quay đầu.' : (result.message || 'Chưa nhận diện được khuôn mặt. Hãy thử lại hoặc liên hệ quản lý.'), 'wf-error');
        if(stage)stage.textContent='Đã dừng · chưa ghi công';
        controls(false); stop();
        showResult();
      }
    } catch (error) { if (current===sequence) { say(error.message, 'wf-error'); controls(false); stop(); showResult(); } }
  }));
})();
