document.addEventListener('DOMContentLoaded', () => {
    // 1. Tab Switching Logic
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const targetId = `tab-${btn.dataset.tab}`;
            const targetContent = document.getElementById(targetId);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });

    // 1b. Navbar Pills Smooth Scrolling & Active Highlight
    const navPills = document.querySelectorAll('.nav-pill-item');
    navPills.forEach(pill => {
        pill.addEventListener('click', (e) => {
            const href = pill.getAttribute('href');
            if (href && href.startsWith('#')) {
                const workspace = document.getElementById('workspace');
                let target = document.querySelector(href);
                
                // If user clicks Video Summary before analyzing a video, take them to the analyzer input
                if (href === '#summary-section' && workspace && workspace.classList.contains('hidden')) {
                    e.preventDefault();
                    navPills.forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    const homeSection = document.getElementById('home');
                    if (homeSection) homeSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    const urlInput = document.getElementById('youtube-url');
                    if (urlInput) {
                        urlInput.focus();
                        urlInput.style.transition = 'background-color 0.3s';
                        urlInput.style.backgroundColor = '#FEF9C3';
                        setTimeout(() => { urlInput.style.backgroundColor = 'transparent'; }, 600);
                    }
                    return;
                }

                if (target) {
                    e.preventDefault();
                    navPills.forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    });

    // 2. File Input Selection Indicator
    const fileInput = document.getElementById('local-file');
    const fileNameDisplay = document.getElementById('file-name-display');
    if (fileInput && fileNameDisplay) {
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                fileNameDisplay.textContent = '📄 ' + e.target.files[0].name;
                fileNameDisplay.style.display = 'inline-block';
            } else {
                fileNameDisplay.textContent = '';
                fileNameDisplay.style.display = 'none';
            }
        });
    }

    // 3. Quick Paste Button
    const pasteBtn = document.getElementById('btn-paste');
    const urlInput = document.getElementById('youtube-url');
    if (pasteBtn && urlInput) {
        pasteBtn.addEventListener('click', async () => {
            try {
                if (navigator.clipboard && navigator.clipboard.readText) {
                    const text = await navigator.clipboard.readText();
                    if (text && text.trim()) {
                        urlInput.value = text.trim();
                        urlInput.focus();
                        return;
                    }
                }
            } catch (err) {
                console.log('Clipboard read permission denied or unavailable, focusing input.');
            }
            urlInput.focus();
            urlInput.select();
        });
    }

    // 4. Curated Demo Notebooks Click Handlers
    const demoChips = document.querySelectorAll('.demo-chip');
    demoChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const url = chip.dataset.url;
            if (url && urlInput) {
                urlInput.value = url;
                
                // Activate URL tab
                const urlTabBtn = document.getElementById('tab-btn-url');
                if (urlTabBtn) urlTabBtn.click();
                
                // Subtle pulse feedback
                urlInput.style.transition = 'background-color 0.3s';
                urlInput.style.backgroundColor = '#FEF9C3';
                setTimeout(() => {
                    urlInput.style.backgroundColor = 'transparent';
                }, 400);
            }
        });
    });

    // 5. Quick Add Button Navigation
    const quickAddBtn = document.getElementById('quick-add-btn');
    if (quickAddBtn) {
        quickAddBtn.addEventListener('click', (e) => {
            e.preventDefault();
            urlInput.focus();
            urlInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    }

    // 6. Form Submission & Kuchu Puchu AI Study Bus Pipeline Controller
    const form = document.getElementById('process-form');
    const heroSection = document.getElementById('home');
    const loadingSection = document.getElementById('loading-section');
    const workspaceSection = document.getElementById('workspace');
    let currentSessionId = null;
    let timerInterval = null;
    let startTime = null;
    let packedItemsCount = 0;

    const STAGES_CONFIG = {
        audio: {
            name: "Processing audio/video",
            icon: "🎧",
            speechActive: "Tuning in! Extracting audio & preparing speech chunks! 🎧",
            speechDone: "Audio extracted & prepped into chunks! ✓"
        },
        whisper: {
            name: "Transcribing with Whisper",
            icon: "🎙️",
            speechActive: "Listening closely! Transcribing spoken words with Whisper! 🎙️",
            speechDone: "Transcription complete and phonetically aligned! ✓"
        },
        summary: {
            name: "Creating the summary",
            icon: "📝",
            speechActive: "Taking notes! Synthesizing key lecture & meeting takeaways! 📝",
            speechDone: "Universal summary & lecture title generated! ✓"
        },
        embedding: {
            name: "Splitting & embedding content",
            icon: "🧩",
            speechActive: "Building memory! Indexing vector embeddings for RAG retrieval! 🧩",
            speechDone: "Semantic vectors indexed in Chroma DB! ✓"
        },
        mindmap: {
            name: "Building the Mind Map",
            icon: "🧠",
            speechActive: "Drawing diagrams! Constructing concept mind map taxonomy! 🧠",
            speechDone: "Interactive Mermaid Mind Map generated! ✓"
        },
        flowchart: {
            name: "Building the Process Flowchart",
            icon: "⚡",
            speechActive: "Tracing workflow! Building procedural logic flowchart! ⚡",
            speechDone: "Step-by-step logic flowchart built! ✓"
        },
        mcq: {
            name: "Generating MCQs",
            icon: "🎯",
            speechActive: "Writing quiz! Drafting practice MCQs & study questions! 🎯",
            speechDone: "Practice quiz & study action items ready! ✓"
        },
        rag: {
            name: "Preparing the RAG chatbot",
            icon: "💬",
            speechActive: "Waking up buddy! Initializing RAG conversational chatbot! 💬",
            speechDone: "Study Buddy online & ready to chat! ✓"
        },
        final: {
            name: "Finalizing results",
            icon: "✨",
            speechActive: "Packing up! Assembling your complete study folio! ✨",
            speechDone: "All stops completed! Kuchu Puchu Study Bus has arrived! 🚀"
        }
    };

    function setDriverSpeech(leadText, detailText) {
        const bubbleLead = document.getElementById('bubble-lead');
        const bubbleDetail = document.getElementById('bubble-detail');
        if (bubbleLead) bubbleLead.textContent = leadText;
        if (bubbleDetail) bubbleDetail.textContent = detailText;
    }

    function startPipelineTimer() {
        startTime = Date.now();
        const timerElem = document.getElementById('bus-elapsed-time');
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            if (!timerElem) return;
            const elapsedSec = Math.floor((Date.now() - startTime) / 1000);
            const mins = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
            const secs = String(elapsedSec % 60).padStart(2, '0');
            timerElem.textContent = `${mins}:${secs}`;
        }, 1000);
    }

    function stopPipelineTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
    }

    function resetStudyBusUI() {
        packedItemsCount = 0;
        const busUnit = document.getElementById('study-bus-unit');
        if (busUnit) {
            busUnit.classList.remove('bus-departing');
        }

        const progressFill = document.getElementById('bus-progress-fill');
        const progressPct = document.getElementById('bus-progress-pct');
        const legacyFill = document.querySelector('.progress-fill');
        if (progressFill) progressFill.style.width = '6%';
        if (legacyFill) legacyFill.style.width = '6%';
        if (progressPct) progressPct.textContent = '0%';

        const timerElem = document.getElementById('bus-elapsed-time');
        if (timerElem) timerElem.textContent = '00:00';

        setDriverSpeech("Honk honk! Engine started! 🚌", "Starting audio/video extraction for your lecture...");

        const luggageCounter = document.getElementById('bus-luggage-counter');
        const cargoTag = document.getElementById('cargo-status-tag');
        if (luggageCounter) luggageCounter.textContent = '0';
        if (cargoTag) cargoTag.textContent = '0 / 9 Loaded';

        Object.keys(STAGES_CONFIG).forEach((stageId, idx) => {
            const slot = document.getElementById(`cargo-slot-${stageId}`);
            if (slot) {
                slot.classList.remove('loaded');
                const mark = slot.querySelector('.slot-mark');
                if (mark) mark.textContent = '○';
            }

            const card = document.getElementById(`task-${stageId}`);
            const chip = document.getElementById(`chip-${stageId}`);
            const check = document.getElementById(`check-${stageId}`);
            const detail = document.getElementById(`detail-${stageId}`);

            if (card) {
                card.classList.remove('active', 'completed');
                if (idx === 0) {
                    card.classList.add('active');
                } else {
                    card.classList.add('pending');
                }
            }
            if (chip) {
                if (idx === 0) {
                    chip.className = 'stop-status-chip active-chip';
                    chip.innerHTML = '<span class="chip-gear-spin">⚙️</span><span>Working...</span>';
                } else {
                    chip.className = 'stop-status-chip pending-chip';
                    chip.innerHTML = '<span>⏳ In line</span>';
                }
            }
            if (check) check.textContent = '○';
            if (detail) detail.textContent = idx === 0 ? 'Starting audio analysis...' : 'Awaiting previous stop...';
        });
    }

    function handlePipelineEvent(event) {
        if (!event) return;

        if (event.status === 'error') {
            throw new Error(event.message || 'Pipeline processing error');
        }

        const stageId = event.stage_id;
        const isCompleted = event.status === 'completed';
        const isProcessing = event.status === 'processing';
        const stageConf = STAGES_CONFIG[stageId] || { 
            name: event.title || stageId, 
            icon: "✦", 
            speechActive: event.detail || "Working...", 
            speechDone: event.detail || "Done!" 
        };

        // Update progress bar
        if (event.progress !== undefined) {
            const progressFill = document.getElementById('bus-progress-fill');
            const progressPct = document.getElementById('bus-progress-pct');
            const legacyFill = document.querySelector('.progress-fill');
            const pct = Math.min(100, Math.max(6, event.progress));
            if (progressFill) progressFill.style.width = `${pct}%`;
            if (legacyFill) legacyFill.style.width = `${pct}%`;
            if (progressPct) progressPct.textContent = `${event.progress}%`;
        }

        const card = document.getElementById(`task-${stageId}`);
        const chip = document.getElementById(`chip-${stageId}`);
        const check = document.getElementById(`check-${stageId}`);
        const detail = document.getElementById(`detail-${stageId}`);

        if (isProcessing) {
            if (card) {
                card.classList.remove('pending', 'completed');
                card.classList.add('active');
            }
            if (chip) {
                chip.className = 'stop-status-chip active-chip';
                chip.innerHTML = '<span class="chip-gear-spin">⚙️</span><span>Working...</span>';
            }
            if (detail && event.detail) {
                detail.textContent = event.detail;
            }
            setDriverSpeech(stageConf.speechActive, event.detail || `Processing stop: ${stageConf.name}...`);
        } else if (isCompleted) {
            if (card) {
                card.classList.remove('pending', 'active');
                card.classList.add('completed');
            }
            if (chip) {
                chip.className = 'stop-status-chip completed-chip';
                chip.innerHTML = '<span>✓ Loaded</span>';
            }
            if (check) check.textContent = '✓';
            if (detail && event.detail) {
                detail.textContent = event.detail;
            }

            // Visually place that task into the bus (Cargo Bay Slot)
            const slot = document.getElementById(`cargo-slot-${stageId}`);
            if (slot && !slot.classList.contains('loaded')) {
                slot.classList.add('loaded');
                const mark = slot.querySelector('.slot-mark');
                if (mark) mark.textContent = '✓';

                packedItemsCount = Math.min(9, packedItemsCount + 1);
                const luggageCounter = document.getElementById('bus-luggage-counter');
                const cargoTag = document.getElementById('cargo-status-tag');
                if (luggageCounter) luggageCounter.textContent = String(packedItemsCount);
                if (cargoTag) cargoTag.textContent = `${packedItemsCount} / 9 Loaded`;
            }

            setDriverSpeech(stageConf.speechDone, event.detail || `${stageConf.name} packed into the bus!`);
        }
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const activeTabElem = document.querySelector('.tab-btn.active');
            const activeTab = activeTabElem ? activeTabElem.dataset.tab : 'url';
            const formData = new FormData();
            formData.append('source_type', activeTab);
            
            const langSelect = document.getElementById('language');
            formData.append('language', langSelect ? langSelect.value : 'english');

            if (activeTab === 'url') {
                const url = urlInput ? urlInput.value.trim() : '';
                if (!url) {
                    alert('Please enter a YouTube video URL.');
                    urlInput.focus();
                    return;
                }
                formData.append('url', url);
            } else {
                const file = fileInput && fileInput.files ? fileInput.files[0] : null;
                if (!file) {
                    alert('Please select an audio or video file to analyze.');
                    return;
                }
                formData.append('file', file);
            }

            // Reset and show Kuchu Puchu Study Bus loading screen
            resetStudyBusUI();
            heroSection.classList.add('hidden');
            loadingSection.classList.remove('hidden');
            
            // Scroll cleanly so the entire top section is fully visible below the navbar
            requestAnimationFrame(() => {
                const navWrapper = document.querySelector('.top-nav-wrapper');
                const navHeight = navWrapper ? navWrapper.offsetHeight : 70;
                const targetY = Math.max(0, loadingSection.getBoundingClientRect().top + window.pageYOffset - navHeight - 24);
                window.scrollTo({ top: targetY, behavior: 'smooth' });
            });

            startPipelineTimer();

            try {
                const response = await fetch('/api/process', {
                    method: 'POST',
                    headers: {
                        'Accept': 'text/event-stream'
                    },
                    body: formData
                });

                if (!response.ok) {
                    let errMsg = 'Processing failed';
                    try {
                        const err = await response.json();
                        errMsg = err.detail || err.message || errMsg;
                    } catch (e) {
                        errMsg = await response.text();
                    }
                    throw new Error(errMsg);
                }

                // Check if response is streaming SSE
                const contentType = response.headers.get('content-type') || '';
                let finalResultData = null;

                if (contentType.includes('text/event-stream') && response.body) {
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const blocks = buffer.split('\n\n');
                        buffer = blocks.pop(); // keep trailing incomplete chunk

                        for (const block of blocks) {
                            const trimmed = block.trim();
                            if (!trimmed) continue;

                            const lines = trimmed.split('\n');
                            for (const line of lines) {
                                if (line.startsWith('data:')) {
                                    const jsonStr = line.replace(/^data:\s*/, '').trim();
                                    if (jsonStr) {
                                        try {
                                            const eventData = JSON.parse(jsonStr);
                                            handlePipelineEvent(eventData);

                                            if (eventData.stage_id === 'final' && eventData.status === 'completed' && eventData.data) {
                                                finalResultData = eventData.data;
                                            }
                                        } catch (parseErr) {
                                            console.warn('Failed to parse SSE payload:', parseErr, jsonStr);
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    // Fallback JSON response handling
                    finalResultData = await response.json();
                    Object.keys(STAGES_CONFIG).forEach(s => {
                        handlePipelineEvent({ stage_id: s, status: 'completed', progress: 100 });
                    });
                }

                if (!finalResultData) {
                    throw new Error('Pipeline completed without returning folio data.');
                }

                stopPipelineTimer();
                currentSessionId = finalResultData.session_id;

                // Progress to 100%
                const progressFill = document.getElementById('bus-progress-fill');
                const progressPct = document.getElementById('bus-progress-pct');
                if (progressFill) progressFill.style.width = '100%';
                if (progressPct) progressPct.textContent = '100%';

                setDriverSpeech("All 9 stops complete! Vroooom! 🚀", "Departing now — your Study Folio is ready!");

                // Animate the bus leaving
                const busUnit = document.getElementById('study-bus-unit');
                if (busUnit) {
                    busUnit.classList.add('bus-departing');
                }

                // Populate workspace
                populateWorkspace(finalResultData);

                // Smoothly transition to results page after bus drive-off animation
                setTimeout(() => {
                    loadingSection.classList.add('hidden');
                    workspaceSection.classList.remove('hidden');
                    workspaceSection.scrollIntoView({ behavior: 'smooth' });
                }, 1000);

            } catch (error) {
                stopPipelineTimer();
                console.error('Analysis error:', error);
                alert('Analysis Error: ' + error.message);
                loadingSection.classList.add('hidden');
                heroSection.classList.remove('hidden');
                heroSection.scrollIntoView({ behavior: 'smooth' });
            }
        });
    }

    let cachedData = null;
    let quizScore = 0;
    let quizAnsweredCount = 0;
    let quizTotalQuestions = 0;

    function populateWorkspace(data) {
        cachedData = data;
        
        const titleElem = document.getElementById('result-title');
        if (titleElem) titleElem.textContent = data.title || "Lecture & Meeting Summary";
        
        const summaryElem = document.getElementById('result-summary');
        if (summaryElem) summaryElem.innerHTML = marked.parse(data.summary || "No summary provided.");
        
        const actionsElem = document.getElementById('result-action-items');
        if (actionsElem) actionsElem.innerHTML = marked.parse(data.action_items || "No explicit action items detected.");
        
        const decisionsElem = document.getElementById('result-decisions');
        if (decisionsElem) decisionsElem.innerHTML = marked.parse(data.key_decisions || "No key decisions recorded.");
        
        const questionsElem = document.getElementById('result-questions');
        if (questionsElem) questionsElem.innerHTML = marked.parse(data.open_questions || "No open questions found.");

        // Interactive MCQ Quiz Builder
        setupInteractiveQuiz(data.mcq_quiz);

        // Mermaid Graphs
        const mmContainer = document.getElementById('result-mind-map');
        if (mmContainer) {
            renderMermaidDiagram(mmContainer, data.mind_map, 'mindmap');
        }

        const fcContainer = document.getElementById('result-flowchart');
        if (fcContainer) {
            renderMermaidDiagram(fcContainer, data.flowchart, 'flowchart');
        }
    }

    // Safe HTML escape helper
    function escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Robust Mermaid Diagram Renderer
    async function renderMermaidDiagram(container, rawCode, idPrefix) {
        if (!container) return;
        if (!rawCode || !rawCode.trim()) {
            container.innerHTML = '<p class="handwritten" style="color: #888; padding: 1.5rem; text-align: center;">No diagram data generated for this session.</p>';
            return;
        }

        let code = rawCode.replace(/```mermaid/g, '').replace(/```/g, '').trim();
        const uniqueId = `${idPrefix}_${Date.now()}_${Math.floor(Math.random() * 10000)}`;

        if (window.mermaid && typeof window.mermaid.render === 'function') {
            try {
                container.removeAttribute('data-processed');
                const { svg } = await window.mermaid.render(uniqueId, code);
                container.innerHTML = svg;
                return;
            } catch (err) {
                console.warn(`Mermaid render notice for ${idPrefix}:`, err);
                const ghostEl = document.getElementById(uniqueId) || document.getElementById('d' + uniqueId);
                if (ghostEl) ghostEl.remove();
            }
        }

        // Clean fallback outline if rendering encounters any client engine issue
        container.innerHTML = `
            <div class="diagram-clean-fallback">
                <div class="diagram-fallback-label">Mermaid Blueprint</div>
                <pre>${escapeHtml(code)}</pre>
            </div>
        `;
    }

    // ========================================================
    // Interactive Quiz Engine (Refined Paper Card & Instant Reveal)
    // ========================================================
    function setupInteractiveQuiz(rawQuizData) {
        const quizContainer = document.getElementById('result-quiz');
        if (!quizContainer) return;
        quizContainer.innerHTML = '';

        let parsedQuiz = [];
        try {
            let cleanJsonStr = (rawQuizData || '').replace(/```json/g, '').replace(/```/g, '').trim();
            parsedQuiz = JSON.parse(cleanJsonStr);
        } catch (e) {
            console.warn('Quiz JSON parse notice, attempting fallback or regex recovery:', e);
            if (rawQuizData) {
                quizContainer.innerHTML = `<div class="quiz-fallback-markdown markdown-body">${marked.parse(rawQuizData)}</div>`;
            }
            return;
        }

        if (!Array.isArray(parsedQuiz) || parsedQuiz.length === 0) {
            quizContainer.innerHTML = '<p class="handwritten" style="padding: 1.5rem; color: #888;">No quiz questions generated for this audio segment.</p>';
            return;
        }

        parsedQuiz.forEach((q, index) => {
            const card = document.createElement('div');
            card.className = 'quiz-card-item';
            card.dataset.index = index;

            const letters = ['A', 'B', 'C', 'D'];
            let optionsHtml = '';

            if (q.options && Array.isArray(q.options)) {
                q.options.forEach((opt, optIdx) => {
                    const letter = letters[optIdx] || String(optIdx + 1);
                    // Strip existing "A)", "A.", "1.", if present in option string
                    let cleanOpt = opt.replace(/^[A-Da-d0-9][\.\)]\s*/, '').trim();

                    optionsHtml += `
                        <button type="button" class="quiz-opt-btn" data-opt-idx="${optIdx}" data-letter="${letter}">
                            <span class="opt-badge">${letter}</span>
                            <span class="opt-text">${escapeHtml(cleanOpt)}</span>
                            <span class="opt-status-chip"></span>
                        </button>
                    `;
                });
            }

            card.innerHTML = `
                <h3 class="quiz-question-title">
                    <span class="quiz-q-num">Q${index + 1}</span>
                    <span class="quiz-q-text">${escapeHtml(q.question)}</span>
                </h3>
                <div class="quiz-options-group">
                    ${optionsHtml}
                </div>
                <div class="quiz-feedback-wrapper" style="display: none;"></div>
            `;

            // Determine the true correct option index
            const rawAnswer = (q.answer || '').trim();
            const cleanAnswer = rawAnswer.replace(/^[A-Da-d0-9][\.\)]\s*/, '').trim().toLowerCase();
            
            let correctOptIdx = -1;
            if (q.options && Array.isArray(q.options)) {
                q.options.forEach((opt, optIdx) => {
                    const letter = letters[optIdx] || String(optIdx + 1);
                    const cleanOpt = opt.replace(/^[A-Da-d0-9][\.\)]\s*/, '').trim().toLowerCase();
                    if (
                        rawAnswer.toUpperCase() === letter.toUpperCase() ||
                        cleanOpt === cleanAnswer ||
                        rawAnswer.toUpperCase().startsWith(letter.toUpperCase() + ')') ||
                        rawAnswer.toUpperCase().startsWith(letter.toUpperCase() + '.') ||
                        (cleanAnswer.length > 3 && (cleanOpt.includes(cleanAnswer) || cleanAnswer.includes(cleanOpt)))
                    ) {
                        correctOptIdx = optIdx;
                    }
                });
            }

            // Build human-friendly formatted correct answer string
            let formattedCorrectAnswer = rawAnswer;
            if (correctOptIdx >= 0 && q.options[correctOptIdx]) {
                const optLetter = letters[correctOptIdx] || String(correctOptIdx + 1);
                const optCleanText = q.options[correctOptIdx].replace(/^[A-Da-d0-9][\.\)]\s*/, '').trim();
                formattedCorrectAnswer = `Option ${optLetter}: ${optCleanText}`;
            }

            // Setup option click listeners for immediate reveal
            const optionBtns = card.querySelectorAll('.quiz-opt-btn');
            const feedbackWrapper = card.querySelector('.quiz-feedback-wrapper');
            let answered = false;

            optionBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    if (answered) return;
                    answered = true;

                    const clickedIdx = parseInt(btn.dataset.optIdx, 10);
                    const isCorrect = (correctOptIdx >= 0) ? (clickedIdx === correctOptIdx) : (() => {
                        const clickedText = btn.querySelector('.opt-text').textContent.trim().toLowerCase();
                        const clickedLetter = btn.dataset.letter;
                        return cleanAnswer === clickedText || rawAnswer.toUpperCase() === clickedLetter.toUpperCase();
                    })();

                    if (isCorrect) {
                        btn.classList.add('is-correct');
                        const chip = btn.querySelector('.opt-status-chip');
                        if (chip) {
                            chip.textContent = '✓ Correct';
                            chip.style.display = 'inline-block';
                        }
                    } else {
                        btn.classList.add('is-wrong');
                        const chip = btn.querySelector('.opt-status-chip');
                        if (chip) {
                            chip.textContent = '✗ Incorrect';
                            chip.style.display = 'inline-block';
                        }

                        // Reveal correct answer on the matching option button
                        if (correctOptIdx >= 0 && optionBtns[correctOptIdx]) {
                            const correctBtn = optionBtns[correctOptIdx];
                            correctBtn.classList.add('is-revealed-correct');
                            const correctChip = correctBtn.querySelector('.opt-status-chip');
                            if (correctChip) {
                                correctChip.textContent = '✓ Correct Answer';
                                correctChip.style.display = 'inline-block';
                            }
                        }
                    }

                    // Lock all options for this question
                    optionBtns.forEach(b => {
                        b.classList.add('locked');
                        b.disabled = true;
                    });

                    // Build and inject immediate feedback card
                    feedbackWrapper.innerHTML = `
                        <div class="quiz-feedback-box ${isCorrect ? 'correct-box' : 'wrong-box'}">
                            <div class="quiz-feedback-header ${isCorrect ? 'feedback-success' : 'feedback-error'}">
                                <span class="feedback-badge-icon">${isCorrect ? '🎉' : '💡'}</span>
                                <span class="feedback-verdict-text">${isCorrect ? 'Correct! Excellent recall.' : 'Incorrect choice'}</span>
                            </div>
                            <div class="quiz-feedback-row">
                                <span class="quiz-feedback-label">Correct Answer:</span>
                                <span class="quiz-feedback-val">${escapeHtml(formattedCorrectAnswer)}</span>
                            </div>
                            <div class="quiz-feedback-row">
                                <span class="quiz-feedback-label">Explanation:</span>
                                <p class="quiz-feedback-exp">${escapeHtml(q.explanation || 'Synthesized directly from the analyzed transcript context.')}</p>
                            </div>
                        </div>
                    `;
                    feedbackWrapper.style.display = 'block';
                });
            });

            quizContainer.appendChild(card);
        });
    }

    // ========================================================
    // Quick Actions: Print Notes (PDF Export) & Ask Study Buddy
    // ========================================================
    const printNotesBtn = document.getElementById('btn-print-notes');
    if (printNotesBtn) {
        printNotesBtn.addEventListener('click', async () => {
            const titleElem = document.getElementById('result-title');
            const titleText = titleElem ? titleElem.textContent.trim() : 'Lecture & Meeting Summary';
            const summaryElem = document.getElementById('result-summary');

            if (!summaryElem || !summaryElem.innerHTML.trim()) {
                alert('No summary content available to export.');
                return;
            }

            const originalHtml = printNotesBtn.innerHTML;
            printNotesBtn.disabled = true;
            printNotesBtn.innerHTML = `
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="spin-icon">
                    <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
                    <path d="M12 2a10 10 0 0 1 10 10"></path>
                </svg>
                <span>Generating PDF...</span>
            `;

            const safeFilename = titleText
                .replace(/[^a-zA-Z0-9_\- ]/g, '')
                .trim()
                .replace(/\s+/g, '_') || 'Summary';

            // Build dedicated high-res printable wrapper
            const printDoc = document.createElement('div');
            printDoc.className = 'pdf-render-document';
            printDoc.innerHTML = `
                <div class="pdf-header">
                    <div class="pdf-brand-mark">
                        <span class="pdf-logo">✦ Kuchu Puchu AI</span>
                        <span class="pdf-tag">Study Companion &amp; Curated Knowledge</span>
                    </div>
                    <h1 class="pdf-doc-title">${escapeHtml(titleText)}</h1>
                    <div class="pdf-doc-meta">
                        <span>Generated on: ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</span>
                        <span>•</span>
                        <span>Universal Video &amp; Meeting Synthesis</span>
                    </div>
                </div>
                <div class="pdf-body markdown-body">
                    ${summaryElem.innerHTML}
                </div>
                <div class="pdf-footer">
                    <span>Kuchu Puchu AI — Complete Universal Summary &amp; Study Notes</span>
                </div>
            `;

            if (typeof html2pdf !== 'undefined') {
                const opt = {
                    margin: [12, 14, 14, 14],
                    filename: `${safeFilename}_Summary.pdf`,
                    image: { type: 'jpeg', quality: 0.98 },
                    html2canvas: { scale: 2, useCORS: true, letterRendering: true, logging: false },
                    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
                    pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
                };

                try {
                    await html2pdf().set(opt).from(printDoc).save();
                    printNotesBtn.innerHTML = `
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                        <span>✓ PDF Downloaded!</span>
                    `;
                    setTimeout(() => {
                        printNotesBtn.innerHTML = originalHtml;
                        printNotesBtn.disabled = false;
                    }, 2200);
                } catch (err) {
                    console.error('PDF generation error, falling back to window.print():', err);
                    window.print();
                    printNotesBtn.innerHTML = originalHtml;
                    printNotesBtn.disabled = false;
                }
            } else {
                window.print();
                printNotesBtn.innerHTML = originalHtml;
                printNotesBtn.disabled = false;
            }
        });
    }

    // Ask Study Buddy click handler: Smooth scroll + focus input with visual pulse
    const askBuddyBtn = document.getElementById('btn-ask-buddy');
    if (askBuddyBtn) {
        askBuddyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const chatSection = document.getElementById('chat-section');
            if (chatSection) {
                chatSection.scrollIntoView({ behavior: 'smooth' });
                setTimeout(() => {
                    const input = document.getElementById('chat-input');
                    if (input) {
                        input.focus();
                        input.classList.add('input-pulse-focus');
                        setTimeout(() => input.classList.remove('input-pulse-focus'), 1200);
                    }
                }, 400);
            }
        });
    }

    // Copy Mermaid buttons
    document.addEventListener('click', (e) => {
        const copyBtn = e.target.closest('.btn-copy-mermaid');
        if (copyBtn && cachedData) {
            const target = copyBtn.dataset.target;
            const rawCode = target === 'result-mind-map' ? cachedData.mind_map : cachedData.flowchart;
            if (rawCode) {
                navigator.clipboard.writeText(rawCode).then(() => {
                    const span = copyBtn.querySelector('span');
                    const orig = span ? span.textContent : 'Copy Syntax';
                    if (span) span.textContent = '✓ Copied!';
                    setTimeout(() => {
                        if (span) span.textContent = orig;
                    }, 2000);
                });
            }
        }
    });

    // Quick Suggested Prompt Chips for RAG
    const promptChips = document.querySelectorAll('.rag-prompt-chip');
    const chatInput = document.getElementById('chat-input');
    const chatForm = document.getElementById('chat-form');

    promptChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const prompt = chip.dataset.prompt;
            if (prompt && chatInput && chatForm) {
                chatInput.value = prompt;
                chatInput.focus();
                // Submit form directly
                chatForm.dispatchEvent(new Event('submit', { cancelable: true }));
            }
        });
    });

    // ========================================================
    // 7. RAG Semantic Chat Interaction
    // ========================================================
    const chatHistory = document.getElementById('chat-history');

    if (chatForm && chatInput && chatHistory) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg || !currentSessionId) {
                if (!currentSessionId) alert('Please analyze a video or file first to initialize the RAG vector co-pilot.');
                return;
            }

            // Append User message
            addChatMsg(msg, 'user-speech-bubble', '🧑 You');
            chatInput.value = '';

            // Append Thinking bubble
            const thinkingId = `thinking_${Date.now()}`;
            addThinkingBubble(thinkingId);

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: currentSessionId,
                        question: msg
                    })
                });

                removeThinkingBubble(thinkingId);

                if (!res.ok) throw new Error('Chat co-pilot query failed');
                const data = await res.json();
                addChatMsg(data.answer, 'bot-speech-bubble', '🤖 Kuchu Puchu AI');
            } catch(e) {
                removeThinkingBubble(thinkingId);
                addChatMsg('⚠️ Error: ' + e.message, 'bot-speech-bubble', '🤖 Kuchu Puchu AI');
            }
        });
    }

    function addThinkingBubble(id) {
        const div = document.createElement('div');
        div.className = 'chat-speech-bubble bot-speech-bubble thinking-bubble';
        div.id = id;
        div.innerHTML = `
            <div class="speech-avatar">🤖</div>
            <div class="speech-body">
                <div class="speech-author">Kuchu Puchu AI</div>
                <div class="speech-text">
                    <span class="thinking-dots">
                        <span></span><span></span><span></span>
                    </span>
                    <em style="color: #7A7264; font-size: 0.88rem; margin-left: 0.5rem;">Searching transcript vectors...</em>
                </div>
            </div>
        `;
        chatHistory.appendChild(div);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function removeThinkingBubble(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function addChatMsg(text, className, author) {
        const div = document.createElement('div');
        div.className = `chat-speech-bubble ${className}`;
        
        const avatar = author.includes('You') ? '🧑' : '🤖';
        const parsedHtml = marked.parse(text);

        div.innerHTML = `
            <div class="speech-avatar">${avatar}</div>
            <div class="speech-body">
                <div class="speech-header-row">
                    <span class="speech-author">${escapeHtml(author)}</span>
                    <button type="button" class="btn-copy-bubble" title="Copy response">📋</button>
                </div>
                <div class="speech-text markdown-body">
                    ${parsedHtml}
                </div>
            </div>
        `;

        const copyBtn = div.querySelector('.btn-copy-bubble');
        if (copyBtn) {
            copyBtn.onclick = () => {
                navigator.clipboard.writeText(text);
                copyBtn.textContent = '✓';
                setTimeout(() => { copyBtn.textContent = '📋'; }, 1500);
            };
        }

        chatHistory.appendChild(div);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
});
