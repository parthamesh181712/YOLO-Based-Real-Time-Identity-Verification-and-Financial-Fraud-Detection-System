const API_BASE = 'http://127.0.0.1:8000';
const video = document.getElementById('video');
const challengeText = document.getElementById('challengeText');
const challengeSubtext = document.getElementById('challengeSubtext');
const sessionBadge = document.getElementById('sessionBadge');
const goToAmlBtn = document.getElementById('goToAmlBtn');
const navButtons = document.querySelectorAll('.nav-chip');
const amlForm = document.getElementById('amlForm');
const amlSubmitButton = amlForm.querySelector('button[type="submit"]');
let authToken = '';
let lastCustomerId = '';
let kycVerified = false;

function clearErrors(form) {
    form.querySelectorAll('.has-error').forEach(el => el.classList.remove('has-error'));
    form.querySelectorAll('.inline-error').forEach(el => el.remove());
}

function showError(input, message) {
    input.classList.add('has-error');
    const err = document.createElement('div');
    err.className = 'inline-error show';
    err.textContent = message;
    input.parentNode.insertBefore(err, input.nextSibling);
}

function validateForm(form) {
    clearErrors(form);
    let valid = true;
    form.querySelectorAll('input[required], select[required]').forEach(input => {
        if (!input.value.trim()) {
            showError(input, 'This field is required');
            valid = false;
        }
    });
    return valid;
}

navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
        if (video) video.srcObject = stream;
    })
    .catch(() => {});

function setDefaultTransactionDate() {
    const input = document.querySelector('#amlForm [name="transaction_date"]');
    if (!input || input.value) return;

    const now = new Date();
    const pad = value => String(value).padStart(2, '0');
    input.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function setActiveNav(screenId) {
    navButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.screen === screenId);
    });
}

function showScreen(id) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    setActiveNav(id);
    if (id === 'amlScreen') {
        setDefaultTransactionDate();
    }
}

navButtons.forEach(button => {
    button.addEventListener('click', () => {
        const target = button.dataset.screen;
        if (!authToken && target !== 'authScreen') {
            showScreen('authScreen');
            return;
        }
        showScreen(target);
    });
});

goToAmlBtn.addEventListener('click', () => showScreen('amlScreen'));

function authHeaders() {
    return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

function captureFrame() {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise(resolve => canvas.toBlob(blob => resolve(blob), 'image/jpeg'));
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function speakInstruction(message) {
    challengeText.textContent = message;

    return new Promise(resolve => {
        if (!window.speechSynthesis) {
            resolve();
            return;
        }

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.rate = 0.9;
        utterance.pitch = 1.0;
        utterance.onend = () => resolve();
        utterance.onerror = () => resolve();
        window.speechSynthesis.speak(utterance);

        setTimeout(resolve, Math.max(2200, message.length * 70));
    });
}

async function promptAndCapture(message, delayBeforeCapture = 2200) {
    challengeSubtext.textContent = 'Listen to the voice instruction and perform the action before the capture happens.';
    await speakInstruction(message);
    await wait(delayBeforeCapture);
    return captureFrame();
}

async function runLivenessChallenge() {
    const direction = Math.random() > 0.5 ? 'TURN_LEFT' : 'TURN_RIGHT';
    const directionText = direction === 'TURN_LEFT'
        ? 'Please turn to your left slowly.'
        : 'Please turn to your right slowly.';
    const blinkText = 'Please blink your eyes now.';

    challengeSubtext.textContent = 'Follow each text and audio instruction carefully. The system waits before each capture.';

    const baseFrame = await promptAndCapture('Look straight at the camera and hold still.', 2500);
    await wait(1200);

    const moveFrame = await promptAndCapture(directionText, 3200);
    await wait(1500);

    const blinkFrame = await promptAndCapture(blinkText, 2600);
    await wait(1000);

    await speakInstruction('Liveness capture complete. KYC verification is being submitted now.');

    return {
        actions: [direction, 'BLINK'],
        frames: { baseFrame, moveFrame, blinkFrame }
    };
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validateForm(e.target)) return;

    const form = new FormData(e.target);
    const payload = Object.fromEntries(form.entries());
    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Authenticating...';

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        const target = document.getElementById('loginResult');

        if (!res.ok) {
            target.innerHTML = `<h3 class="error">Login failed</h3><p>${data.detail}</p>`;
            sessionBadge.textContent = 'Login Failed';
            return;
        }

        authToken = data.access_token;
        sessionBadge.textContent = `Logged in: ${data.user.username}`;
        target.innerHTML = `<h3 class="success">Logged in as ${data.user.username}</h3><p>Role: ${data.user.role}</p>`;
        setTimeout(() => showScreen('kycScreen'), 800);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
});

document.getElementById('kycForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validateForm(e.target)) return;

    challengeText.textContent = 'Preparing liveness check...';
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;

    try {
        const liveness = await runLivenessChallenge();
        btn.textContent = 'Verifying...';
        const formData = new FormData(e.target);
        formData.append('live', liveness.frames.baseFrame, 'live_base.jpg');
        formData.append('live2', liveness.frames.moveFrame, 'live_move.jpg');
        formData.append('live3', liveness.frames.blinkFrame, 'live_blink.jpg');
        formData.append('liveness_actions', liveness.actions.join(','));

        const res = await fetch(`${API_BASE}/kyc/verify`, {
            method: 'POST',
            headers: authHeaders(),
            body: formData
        });
        const data = await res.json();
        const resultDiv = document.getElementById('kycResult');

    if (!res.ok || data.kyc_status !== 'VERIFIED') {
        const reasons = data.reason_codes || data.kyc_reasons || [];
        kycVerified = false;
        goToAmlBtn.classList.add('hidden');
        resultDiv.innerHTML = `
            <h3 class="error">KYC Failed</h3>
            <p>${data.detail || data.reason || 'Verification failed'}</p>
            <pre>${JSON.stringify(reasons, null, 2)}</pre>
        `;
        challengeSubtext.textContent = 'Try again and wait for each spoken instruction before moving.';
        return;
    }

    lastCustomerId = data.customer_id;
    kycVerified = true;
    document.querySelector('#amlForm [name="customer_id"]').value = data.customer_id;
    goToAmlBtn.classList.remove('hidden');
    setDefaultTransactionDate();
    resultDiv.innerHTML = `
        <h3 class="success">KYC Verified</h3>
        <p>Request ID: ${data.request_id}</p>
        <p>Confidence: ${data.confidence}</p>
        <p>Liveness Actions: ${data.liveness_actions.join(', ')}</p>
        <pre>${JSON.stringify(data.reason_codes, null, 2)}</pre>
    `;
        challengeSubtext.textContent = 'KYC is complete. AML is available as a separate screen, but you can open AML anytime from the dashboard.';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Verify KYC';
    }
});

amlForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!validateForm(e.target)) return;

    const resultDiv = document.getElementById('amlResult');

    if (!authToken) {
        resultDiv.innerHTML = `<h3 class="error">AML check failed</h3><p>Please log in first.</p>`;
        showScreen('authScreen');
        return;
    }

    const formData = new FormData(e.target);
    const payload = Object.fromEntries(formData.entries());

    if (!payload.transaction_date) {
        setDefaultTransactionDate();
        resultDiv.innerHTML = `<h3 class="warning">Transaction time missing</h3><p>I filled the current date/time for you. Click Check AML once more.</p>`;
        return;
    }

    payload.amount = Number(payload.amount);
    payload.old_balance = Number(payload.old_balance);
    payload.new_balance = Number(payload.new_balance);
    payload.transaction_type = Number(payload.transaction_type);
    payload.transaction_date = new Date(payload.transaction_date).toISOString();

    amlSubmitButton.disabled = true;
    amlSubmitButton.textContent = 'Checking AML...';

    try {
        const res = await fetch(`${API_BASE}/aml/check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        amlSubmitButton.disabled = false;
        amlSubmitButton.textContent = 'Check AML';

    if (!res.ok) {
        resultDiv.innerHTML = `<h3 class="error">AML check failed</h3><p>${data.detail || 'Unknown error'}</p>`;
        return;
    }

    lastCustomerId = data.customer_id;
    document.getElementById('timelineBtn').classList.remove('hidden');
    resultDiv.innerHTML = `
        <h3>${data.status}</h3>
        <p>Decision ID: ${data.decision_id}</p>
        <p>Risk Score: ${data.risk_score}</p>
        <pre>${JSON.stringify(data.reason_codes, null, 2)}</pre>
        <p>Model: ${data.model_version}</p>
        <p>Rules: ${data.rule_engine_version}</p>
        <p>Transaction Type: ${data.transaction_type}</p>
    `;
    } catch (err) {
        amlSubmitButton.disabled = false;
        amlSubmitButton.textContent = 'Check AML';
        resultDiv.innerHTML = `<h3 class="error">Error</h3><p>${err.message}</p>`;
    }
});

document.getElementById('timelineBtn').addEventListener('click', async () => {
    if (!lastCustomerId) return;
    const res = await fetch(`${API_BASE}/customers/${lastCustomerId}/timeline`, {
        headers: authHeaders()
    });
    const data = await res.json();
    const target = document.getElementById('timelineResult');
    if (!res.ok) {
        target.innerHTML = `<h3 class="error">Timeline failed</h3><p>${data.detail || 'Unknown error'}</p>`;
        return;
    }
    target.innerHTML = `<h3>Customer Timeline</h3><pre>${JSON.stringify(data.timeline, null, 2)}</pre>`;
});

setDefaultTransactionDate();
