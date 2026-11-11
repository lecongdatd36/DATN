(() => {
    'use strict';
    const root = document.querySelector('[data-face-test]');
    if (!root) return;
    const find = selector => root.querySelector(selector);
    const config = JSON.parse(document.getElementById('face-test-config').textContent);
    const video = find('video'), startButton = find('[data-camera-start]');
    const detectButton = find('[data-face-detect]'), stopButton = find('[data-camera-stop]');
    const enabled = !startButton.disabled;
    const card = find('[data-result-card]'), metric = find('.ft-match-metric');
    const canvas = document.createElement('canvas');
    let stream = null, controller = null, generation = 0, busy = false;
    const score = value => typeof value === 'number' && Number.isFinite(value)
        ? value.toLocaleString('vi-VN', {minimumFractionDigits: 3, maximumFractionDigits: 3}) : '—';
    find('[data-match-threshold]').textContent = score(config.threshold);
    function result(state, title, message) {
        card.dataset.state = state;
        find('[data-result-title]').textContent = title;
        find('[data-result-message]').textContent = message;
        find('[data-result-symbol]').textContent = {idle: '○', loading: '…', success: '✓', error: '!'}[state];
        find('[data-result-person]').hidden = true;
        find('[data-person-name]').textContent = '';
        find('[data-person-code]').textContent = '';
        find('[data-match-name]').textContent = '—';
        find('[data-match-score]').textContent = '—';
        find('[data-match-label]').textContent = state === 'loading' ? 'ĐANG ĐỐI CHIẾU MẪU' : state === 'error' ? 'CHƯA NHẬN DIỆN ĐƯỢC' : 'CHƯA NHẬN DIỆN';
        find('[data-feed-status]').textContent = title;
        metric.classList.toggle('is-error', state === 'error');
        metric.classList.remove('is-success');
    }
    function stop(message = 'Camera đã dừng. Bật lại để bắt đầu lượt kiểm thử mới.') {
        generation++;
        controller?.abort(); controller = null; busy = false;
        stream?.getTracks().forEach(track => track.stop());
        stream = null; video.srcObject = null;
        startButton.disabled = !enabled; detectButton.disabled = true; stopButton.disabled = true;
        find('[data-camera-placeholder]').hidden = false;
        find('[data-camera-state]').textContent = 'CAMERA CHƯA BẬT';
        find('[data-camera-state]').classList.remove('is-active');
        find('[data-camera-hint]').textContent = 'Camera chưa được bật';
        result('idle', 'Camera đã dừng', message);
    }
    startButton.addEventListener('click', async () => {
        const current = ++generation;
        startButton.disabled = true;
        result('loading', 'Đang mở camera', 'Cho phép trình duyệt sử dụng camera để bắt đầu.');
        try {
            if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
                throw new Error('Camera cần HTTPS hoặc localhost. Hãy mở trang bằng địa chỉ phù hợp.');
            const next = await navigator.mediaDevices.getUserMedia({audio: false,
                video: {width: {ideal: 960}, height: {ideal: 720}, facingMode: 'user'}});
            if (generation !== current) { next.getTracks().forEach(track => track.stop()); return; }
            stream = next; video.srcObject = stream;
            await video.play();
            if (generation !== current) return;
            stream.getVideoTracks()[0]?.addEventListener('ended', () => {
                if (generation === current) stop('Camera đã ngắt kết nối. Kiểm tra thiết bị và bật lại camera.');
            }, {once: true});
            find('[data-camera-placeholder]').hidden = true;
            find('[data-camera-state]').textContent = 'CAMERA TRỰC TIẾP';
            find('[data-camera-state]').classList.add('is-active');
            find('[data-camera-hint]').textContent = 'Nhìn thẳng vào camera';
            detectButton.disabled = false; stopButton.disabled = false;
            result('idle', 'Sẵn sàng nhận diện', 'Giữ yên trong khung, sau đó bấm “Nhận diện thử”.');
        } catch (error) {
            if (generation !== current) return;
            stop();
            const message = error.name === 'NotAllowedError' ? 'Quyền camera bị từ chối. Cho phép camera trong cài đặt của trình duyệt rồi thử lại.'
                : error.name === 'NotFoundError' ? 'Không tìm thấy camera trên thiết bị này.'
                : error.name === 'NotReadableError' ? 'Không mở được camera. Đóng ứng dụng khác đang dùng camera rồi thử lại.' : error.message;
            result('error', 'Chưa mở được camera', message);
        }
    });
    stopButton.addEventListener('click', () => stop());
    detectButton.addEventListener('click', async () => {
        if (busy || !stream?.active) return;
        const current = generation;
        busy = true; detectButton.disabled = true;
        result('loading', 'Đang nhận diện…', 'Đang đối chiếu với mẫu khuôn mặt đã đăng ký. Vui lòng giữ yên.');
        controller = new AbortController();
        const requestController = controller;
        const timeout = setTimeout(() => requestController.abort(), 30000);
        try {
            if (!video.videoWidth || video.readyState < 2) throw new Error('Camera chưa có khung hình. Đợi hình ảnh xuất hiện rồi thử lại.');
            const scale = Math.min(1, 960 / video.videoWidth, 720 / video.videoHeight);
            canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
            canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
            const frame = canvas.toDataURL('image/jpeg', .88);
            const response = await fetch(root.dataset.apiUrl, {method: 'POST', credentials: 'same-origin', cache: 'no-store',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': find('[name=csrfmiddlewaretoken]').value},
                body: JSON.stringify({frame}), signal: requestController.signal});
            if (!response.headers.get('content-type')?.includes('application/json'))
                throw new Error('Phiên đăng nhập hết hạn hoặc máy chủ chưa sẵn sàng. Tải lại trang và đăng nhập để tiếp tục.');
            const data = await response.json();
            if (generation !== current) return;
            if (!response.ok || data.ok !== true) throw new Error(data.message || 'Máy chủ chưa xử lý được khung hình. Vui lòng thử lại.');
            if (data.identified === true && data.name && typeof data.similarity === 'number') {
                result('success', 'Đã nhận diện khuôn mặt', data.message);
                find('[data-result-person]').hidden = false;
                find('[data-person-name]').textContent = data.name;
                find('[data-person-code]').textContent = data.employee_code;
                find('[data-match-name]').textContent = data.name;
                find('[data-match-score]').textContent = score(data.similarity);
                find('[data-match-threshold]').textContent = score(data.threshold);
                find('[data-match-label]').textContent = 'ĐÃ KHỚP MẪU · CHƯA GHI CÔNG';
                metric.classList.add('is-success');
            } else {
                result('error', 'Chưa nhận diện được', data.message || 'Chưa có kết quả khớp mẫu. Kiểm tra mẫu đăng ký và thử lại.');
            }
            find('[data-camera-hint]').textContent = 'Lần kiểm thử: ' + new Date().toLocaleTimeString('vi-VN');
        } catch (error) {
            if (generation !== current) return;
            const message = error.name === 'AbortError' ? 'Máy chủ phản hồi quá chậm. Kiểm tra kết nối rồi thử lại.'
                : error instanceof TypeError ? 'Không kết nối được máy chủ. Kiểm tra kết nối rồi thử lại.' : error.message;
            result('error', 'Chưa nhận diện được', message);
        } finally {
            clearTimeout(timeout); canvas.width = 0; canvas.height = 0;
            if (generation === current) { busy = false; controller = null; detectButton.disabled = !stream?.active; }
        }
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) stop('Đã dừng camera khi bạn rời trang. Bật lại để tiếp tục.'); });
    window.addEventListener('pagehide', () => stop());
})();
