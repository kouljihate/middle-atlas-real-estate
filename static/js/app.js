// Delete confirmation modal
(function () {
    const modal = document.getElementById('deleteModal');
    const form = document.getElementById('deleteForm');
    const titleEl = document.getElementById('modalLandTitle');

    function openModal(endpoint, id, title) {
        form.action = endpoint + '/' + id + '/delete';
        titleEl.textContent = title;
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        modal.hidden = true;
        document.body.style.overflow = '';
    }

    document.querySelectorAll('[data-delete]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            openModal(btn.dataset.endpoint || '/land', btn.dataset.id, btn.dataset.title);
        });
    });

    modal.querySelectorAll('[data-close]').forEach(function (el) {
        el.addEventListener('click', closeModal);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.hidden) closeModal();
    });
})();

// ---------------------------------------------------------------------------
// Press-and-hold voice recorder for the Audio Description field.
// The recorded blob is turned into a File and pushed into the audios input,
// so it is saved through the normal upload path.
// ---------------------------------------------------------------------------
(function () {
    const btn = document.getElementById('recordBtn');
    if (!btn) return;

    const audioInput = document.getElementById('audios');
    const statusEl = document.getElementById('recStatus');
    const preview = document.getElementById('audioPreview');
    if (!audioInput) return;

    let recordedBlobs = [];
    let mediaRecorder = null;
    let stream = null;
    let timer = null;
    let seconds = 0;

    function renderPreview() {
        preview.innerHTML = '';
        recordedBlobs.forEach(function (file, i) {
            const url = URL.createObjectURL(file);
            const label = document.createElement('label');
            label.className = 'chip';
            const audio = document.createElement('audio');
            audio.controls = true;
            audio.src = url;
            const remove = document.createElement('span');
            remove.textContent = '✕';
            remove.className = 'remove-rec';
            remove.title = 'Remove';
            remove.addEventListener('click', function () {
                URL.revokeObjectURL(url);
                recordedBlobs.splice(i, 1);
                syncInput();
            });
            label.appendChild(audio);
            label.appendChild(remove);
            preview.appendChild(label);
        });
    }

    function syncInput() {
        const dt = new DataTransfer();
        recordedBlobs.forEach(function (f) { dt.items.add(f); });
        audioInput.files = dt.files;
        renderPreview();
    }

    function startRec() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            statusEl.textContent = 'Recorder not supported';
            return;
        }
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(function (s) {
                stream = s;
                let options = {};
                if (MediaRecorder.isTypeSupported('audio/webm')) {
                    options = { mimeType: 'audio/webm' };
                }
                mediaRecorder = new MediaRecorder(stream, options);
                const chunks = [];
                mediaRecorder.ondataavailable = function (e) {
                    if (e.data && e.data.size) chunks.push(e.data);
                };
                mediaRecorder.onstop = function () {
                    const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                    const ext = (mediaRecorder.mimeType || '').includes('ogg') ? 'ogg' : 'webm';
                    const file = new File([blob], 'rec_' + Date.now() + '.' + ext, { type: blob.type });
                    recordedBlobs.push(file);
                    syncInput();
                    stream.getTracks().forEach(function (t) { t.stop(); });
                    stopUI();
                };
                mediaRecorder.start();
                startUI();
            })
            .catch(function () {
                statusEl.textContent = 'Microphone access denied';
            });
    }

    function stopRec() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
    }

    function startUI() {
        btn.classList.add('recording');
        seconds = 0;
        statusEl.textContent = '● 0s';
        timer = setInterval(function () {
            seconds += 1;
            statusEl.textContent = '● ' + seconds + 's';
        }, 1000);
    }

    function stopUI() {
        btn.classList.remove('recording');
        if (timer) { clearInterval(timer); timer = null; }
        statusEl.textContent = '';
    }

    btn.addEventListener('pointerdown', function (e) {
        e.preventDefault();
        startRec();
    });
    // Release anywhere stops the recording.
    document.addEventListener('pointerup', stopRec);

    // Also allow picking a file from disk (merged with recordings).
    audioInput.addEventListener('change', function () {
        Array.prototype.forEach.call(audioInput.files, function (f) {
            recordedBlobs.push(f);
        });
        audioInput.value = '';
        syncInput();
    });
})();

// ---------------------------------------------------------------------------
// Affair form: populate the Land select based on the chosen Seller.
// ---------------------------------------------------------------------------
(function () {
    const sellerSel = document.getElementById('seller_id');
    const landSel = document.getElementById('land_id');
    const dataEl = document.getElementById('lands-by-seller');
    if (!sellerSel || !landSel || !dataEl) return;

    let landsBySeller = {};
    try {
        landsBySeller = JSON.parse(dataEl.textContent || '{}');
    } catch (e) {
        landsBySeller = {};
    }

    sellerSel.addEventListener('change', function () {
        const sid = sellerSel.value;
        const opts = landsBySeller[sid] || [];
        const prev = landSel.value;
        landSel.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = landSel.dataset.placeholder || '';
        landSel.appendChild(placeholder);
        opts.forEach(function (l) {
            const o = document.createElement('option');
            o.value = l.id;
            o.textContent = l.title;
            if (String(l.id) === String(prev)) o.selected = true;
            landSel.appendChild(o);
        });
    });
})();
