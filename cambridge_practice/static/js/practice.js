function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift();
    }
    return '';
}

function formatTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const seconds = Math.floor(totalSeconds % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
}

document.addEventListener('DOMContentLoaded', () => {
    const shell = document.querySelector('.practice-shell');
    const form = document.querySelector('#practiceForm');
    if (!shell || !form) {
        return;
    }

    const timerDisplay = document.querySelector('#timerDisplay');
    const saveStatus = document.querySelector('#saveStatus');
    const audio = document.querySelector('#practiceAudio');
    const reviewBanner = document.querySelector('#reviewBanner');
    const reviewTimer = document.querySelector('#reviewTimer');

    const saveUrl = shell.dataset.saveUrl;
    const bookNumber = shell.dataset.bookNumber;
    const testNumber = shell.dataset.testNumber;
    const section = shell.dataset.section;
    const isPreview = shell.dataset.preview === 'true';
    const isListening = section === 'listening';
    const isReading = section === 'reading';
    const defaultDuration = Number(shell.dataset.durationSeconds || 3600);
    let remaining = isReading ? defaultDuration : 0;
    let reviewRemaining = null;
    let completed = shell.dataset.status === 'completed';
    let saveTimeout = null;
    let saveInFlight = false;
    let allowNavigation = false;
    const dragChoiceGroups = [];
    const existingScore = shell.dataset.existingScore || '';
    const existingBand = shell.dataset.existingBand || '';

    if (saveStatus) {
        saveStatus.textContent = isPreview ? 'Preview' : 'Not submitted';
    }

    if (isListening && timerDisplay) {
        timerDisplay.hidden = true;
    }

    function normalizeSubmittedAnswer(value) {
        return String(value || '').trim().toUpperCase();
    }

    function normalizeAnswerInput(input) {
        if (!input || !/^answer_\d+$/.test(input.name || '')) {
            return;
        }

        const normalized = normalizeSubmittedAnswer(input.value);
        if (input.value === normalized) {
            return;
        }

        const canRestoreSelection = input.type !== 'hidden';
        const start = canRestoreSelection ? input.selectionStart : null;
        const end = canRestoreSelection ? input.selectionEnd : null;
        input.value = normalized;
        if (canRestoreSelection && start !== null && end !== null) {
            input.setSelectionRange(start, end);
        }
    }

    function normalizeAllAnswerInputs() {
        form.querySelectorAll('input[name^="answer_"]').forEach(normalizeAnswerInput);
    }

    function collectAnswers() {
        const answers = {};
        for (let index = 1; index <= 40; index += 1) {
            const input = form.querySelector(`[name="answer_${index}"]`);
            if (input) {
                normalizeAnswerInput(input);
            }
            answers[String(index)] = input ? normalizeSubmittedAnswer(input.value) : '';
        }
        return answers;
    }

    function updateFilledBlanks() {
        form.querySelectorAll('.ielts-blank input').forEach((input) => {
            input.closest('.ielts-blank').classList.toggle('has-value', input.value.trim() !== '');
        });
    }

    function updateMultipleChoice() {
        form.querySelectorAll('.mc-question').forEach((group) => {
            const input = group.querySelector('input[type="hidden"]');
            const selected = input ? input.value.trim().toUpperCase() : '';
            group.querySelectorAll('.mc-option').forEach((button) => {
                button.classList.toggle('is-selected', button.dataset.value === selected);
            });
        });
        syncDragChoiceGroups();
    }

    function updateMultiAnswerChoices() {
        form.querySelectorAll('.multi-answer-question').forEach((group) => {
            const inputs = Array.from(group.querySelectorAll('input[type="hidden"]'));
            const selected = inputs.map((input) => input.value.trim().toUpperCase()).filter(Boolean);
            group.querySelectorAll('.multi-option').forEach((button) => {
                button.classList.toggle('is-selected', selected.includes(button.dataset.value));
            });
        });
    }

    function displayAnswer(value) {
        if (Array.isArray(value)) {
            return value.join(' / ');
        }

        return String(value || '');
    }

    function resultTargetFor(input) {
        const inlineBlank = input.closest('.ielts-blank');
        if (inlineBlank) {
            return {
                highlight: inlineBlank,
                badge: inlineBlank,
            };
        }

        const question = input.closest('.mc-question');
        if (question) {
            return {
                highlight: question,
                badge: question,
            };
        }

        const multiQuestion = input.closest('.multi-answer-question');
        if (multiQuestion) {
            const submittedValue = normalizeSubmittedAnswer(input.value);
            if (submittedValue) {
                const selectedOption = Array.from(multiQuestion.querySelectorAll('.multi-option'))
                    .find((button) => button.dataset.value === submittedValue);
                if (selectedOption) {
                    return {
                        highlight: selectedOption,
                        badge: selectedOption,
                    };
                }
            }

            return {
                highlight: multiQuestion,
                badge: multiQuestion,
            };
        }

        const answerField = input.closest('.answer-field');
        return {
            highlight: answerField || input.parentElement,
            badge: answerField || input.parentElement,
        };
    }

    function removeOldResultMarkers() {
        form.querySelectorAll('.answer-correct, .answer-wrong, .answer-skipped').forEach((element) => {
            element.classList.remove('answer-correct', 'answer-wrong', 'answer-skipped');
        });
        form.querySelectorAll('.correct-answer-badge').forEach((element) => element.remove());
    }

    function addCorrectBadge(container, officialAnswer) {
        if (!container) {
            return;
        }

        const badge = document.createElement('span');
        badge.className = 'correct-answer-badge';
        badge.textContent = displayAnswer(officialAnswer);
        if (container.classList && container.classList.contains('ielts-blank')) {
            container.insertAdjacentElement('afterend', badge);
            return;
        }

        container.appendChild(badge);
    }

    function applyResultDetails(details = {}) {
        removeOldResultMarkers();

        Object.entries(details).forEach(([question, detail]) => {
            const input = form.querySelector(`[name="answer_${question}"]`);
            if (!input) {
                return;
            }

            const target = resultTargetFor(input);
            const submitted = String(detail.submitted || '').trim();
            const isSkipped = submitted === '';

            if (detail.correct) {
                target.highlight.classList.add('answer-correct');
            } else if (isSkipped) {
                target.highlight.classList.add('answer-skipped');
                addCorrectBadge(target.badge, detail.official);
            } else {
                target.highlight.classList.add('answer-wrong');
                addCorrectBadge(target.badge, detail.official);
            }
        });
    }

    function showResult(score, totalQuestions, bandScore) {
        const resultDisplay = document.querySelector('#resultDisplay');
        if (!resultDisplay || score === null || score === undefined || score === '') {
            return;
        }

        const bandText = bandScore !== null && bandScore !== undefined && bandScore !== ''
            ? ` | Band ${bandScore}`
            : '';
        resultDisplay.textContent = `${isPreview ? 'Preview score' : 'Score'}: ${score}/${totalQuestions || 40}${bandText}`;
        resultDisplay.hidden = false;
    }

    function completedStatusText(score, totalQuestions, bandScore) {
        const bandText = bandScore !== null && bandScore !== undefined && bandScore !== ''
            ? ` | Band ${bandScore}`
            : '';
        return score !== null && score !== undefined && score !== ''
            ? `Completed: ${score}/${totalQuestions || 40}${bandText}`
            : 'Completed';
    }

    function valueEquals(left, right) {
        return String(left || '').trim().toLowerCase() === String(right || '').trim().toLowerCase();
    }

    function validDragChoiceValue(value) {
        return /^[A-Z]$/.test(value)
            || /^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$/i.test(value);
    }

    function textWithoutFirstStrong(element) {
        const clone = element.cloneNode(true);
        const strong = clone.querySelector('strong');
        if (strong) {
            strong.remove();
        }

        return clone.textContent.replace(/\s+/g, ' ').trim();
    }

    function textBetweenChoiceLabels(paragraph, strong, nextStrong) {
        const range = document.createRange();
        range.setStartAfter(strong);
        if (nextStrong) {
            range.setEndBefore(nextStrong);
        } else if (paragraph.lastChild) {
            range.setEndAfter(paragraph.lastChild);
        } else {
            range.setEndAfter(paragraph);
        }

        const text = range.cloneContents().textContent.replace(/\s+/g, ' ').trim();
        range.detach();
        return text || textWithoutFirstStrong(paragraph);
    }

    function normalizeChoiceBank(bank) {
        if (bank.dataset.choiceBankNormalized === 'true') {
            return;
        }

        Array.from(bank.querySelectorAll('p')).forEach((paragraph) => {
            const labels = Array.from(paragraph.querySelectorAll('strong'))
                .filter((strong) => validDragChoiceValue(strong.textContent.trim()));
            if (labels.length <= 1) {
                return;
            }

            labels.forEach((strong, labelIndex) => {
                const item = document.createElement('p');
                const label = document.createElement('strong');
                const description = document.createElement('span');
                label.textContent = strong.textContent.trim();
                description.textContent = textBetweenChoiceLabels(paragraph, strong, labels[labelIndex + 1]);
                item.append(label, description);
                paragraph.parentNode.insertBefore(item, paragraph);
            });
            paragraph.remove();
        });

        bank.dataset.choiceBankNormalized = 'true';
    }

    function extractChoiceBankItems(bank) {
        normalizeChoiceBank(bank);

        const items = [];
        const paragraphs = Array.from(bank.querySelectorAll('p'));

        paragraphs.forEach((paragraph) => {
            const labels = Array.from(paragraph.querySelectorAll('strong'));

            labels.forEach((strong, labelIndex) => {
                const value = strong.textContent.trim();
                if (!validDragChoiceValue(value)) {
                    return;
                }

                items.push({
                    value,
                    label: value,
                    description: textBetweenChoiceLabels(paragraph, strong, labels[labelIndex + 1]),
                    element: paragraph,
                });
            });
        });

        return items;
    }

    function assignmentValuesMatchBank(container, bankItems) {
        const bankValues = bankItems.map((item) => item.value);
        const optionValues = Array.from(container.querySelectorAll('.mc-options.compact-options .mc-option'))
            .map((button) => button.dataset.value || '')
            .filter(Boolean);

        if (!optionValues.length) {
            return false;
        }

        return optionValues.every((value) => bankValues.some((bankValue) => valueEquals(bankValue, value)));
    }

    function findAssignmentContainerForBank(bank, bankItems) {
        let element = bank.nextElementSibling;
        let scanned = 0;
        const blankAssignmentSelector = '.ielts-report-list, .ielts-facility-list, .sentence-questions, .map-answers, .ielts-note-box, .reading-diagram-card';

        while (element && scanned < 8) {
            const choiceList = element.matches('.reading-choice-list, .ielts-mc-list')
                ? element
                : element.querySelector('.reading-choice-list, .ielts-mc-list');
            if (choiceList && assignmentValuesMatchBank(choiceList, bankItems)) {
                return choiceList;
            }

            const inlineChoiceContainer = element.matches('.ielts-note-box')
                ? element
                : element.querySelector('.ielts-note-box');
            if (inlineChoiceContainer && assignmentValuesMatchBank(inlineChoiceContainer, bankItems)) {
                return inlineChoiceContainer;
            }

            if (
                element.matches('.ielts-choice-box, .scientist-box, .ielts-note-box')
                && extractChoiceBankItems(element).length >= 2
            ) {
                return null;
            }

            const blankAssignmentList = element.matches(blankAssignmentSelector)
                ? element
                : element.querySelector(blankAssignmentSelector);
            if (blankAssignmentList && blankAssignmentList.querySelector('.ielts-blank input')) {
                return blankAssignmentList;
            }

            const answerGrid = element.matches('.answer-grid')
                ? element
                : element.querySelector('.answer-grid');
            if (answerGrid && answerGrid.querySelector('.answer-field input')) {
                return answerGrid;
            }

            element = element.nextElementSibling;
            scanned += 1;
        }

        element = bank.previousElementSibling;
        scanned = 0;
        while (element && scanned < 4) {
            const blankAssignmentList = element.matches(blankAssignmentSelector)
                ? element
                : element.querySelector(blankAssignmentSelector);
            if (blankAssignmentList && blankAssignmentList.querySelector('.ielts-blank input')) {
                return blankAssignmentList;
            }

            if (
                element.matches('.ielts-choice-box, .scientist-box, .ielts-note-box')
                && extractChoiceBankItems(element).length >= 2
            ) {
                return null;
            }

            element = element.previousElementSibling;
            scanned += 1;
        }

        return null;
    }

    function contextAllowsRepeatedChoices(bank, assignmentContainer) {
        let context = bank.textContent + ' ' + assignmentContainer.textContent;
        let element = bank.previousElementSibling;
        let scanned = 0;

        while (element && scanned < 4) {
            context += ` ${element.textContent}`;
            element = element.previousElementSibling;
            scanned += 1;
        }

        return /more than once/i.test(context);
    }

    function canonicalDragValue(group, rawValue) {
        const value = String(rawValue || '').trim();
        const item = group.items.find((candidate) => valueEquals(candidate.value, value));
        return item ? item.value : value;
    }

    function readDragData(event) {
        const customData = event.dataTransfer.getData('application/x-cambridge-choice');
        if (customData) {
            try {
                return JSON.parse(customData);
            } catch (error) {
                return null;
            }
        }

        const fallbackValue = event.dataTransfer.getData('text/plain');
        return fallbackValue ? { value: fallbackValue } : null;
    }

    function setDragData(event, group, value, sourceInput = null) {
        const payload = {
            groupId: group.id,
            value,
            sourceName: sourceInput ? sourceInput.name : '',
        };
        event.dataTransfer.setData('application/x-cambridge-choice', JSON.stringify(payload));
        event.dataTransfer.setData('text/plain', value);
        event.dataTransfer.effectAllowed = 'move';
    }

    function inputForDragTarget(group, target) {
        const inputName = target.dataset.inputName || '';
        return group.inputs.find((input) => input.name === inputName) || null;
    }

    function dragTargetFromPoint(group, x, y) {
        const element = document.elementFromPoint(x, y);
        const target = element ? element.closest('.drag-assignment-target') : null;
        if (!target) {
            return null;
        }

        return inputForDragTarget(group, target) ? target : null;
    }

    function clearDragTargetHighlights(group) {
        group.targets.forEach((target) => {
            target.classList.remove('is-drag-over');
        });
    }

    function updatePointerDragGhost(state, x, y) {
        state.ghost.style.left = `${x}px`;
        state.ghost.style.top = `${y}px`;

        const target = dragTargetFromPoint(state.group, x, y);
        if (state.currentTarget !== target) {
            clearDragTargetHighlights(state.group);
            state.currentTarget = target;
            if (target) {
                target.classList.add('is-drag-over');
            }
        }
    }

    function createPointerDragGhost(value, description) {
        const ghost = document.createElement('div');
        ghost.className = 'drag-choice-ghost';
        ghost.innerHTML = `<strong>${value}</strong><span>${description || ''}</span>`;
        document.body.appendChild(ghost);
        return ghost;
    }

    function startPointerDrag(event, group, value, sourceInput = null, sourceElement = null) {
        if (completed || (sourceElement && sourceElement.hidden)) {
            return;
        }
        if (event.pointerType === 'mouse' && event.button !== 0) {
            return;
        }

        const item = group.items.find((candidate) => valueEquals(candidate.value, value));
        const ghost = createPointerDragGhost(value, item?.description || '');
        const state = {
            group,
            value,
            sourceInput,
            sourceElement,
            ghost,
            currentTarget: null,
        };

        event.preventDefault();
        sourceElement?.classList.add('is-dragging');
        updatePointerDragGhost(state, event.clientX, event.clientY);

        function finishDrag(pointerEvent) {
            const target = dragTargetFromPoint(group, pointerEvent.clientX, pointerEvent.clientY);
            const input = target ? inputForDragTarget(group, target) : null;
            const elementAtDrop = document.elementFromPoint(pointerEvent.clientX, pointerEvent.clientY);
            const droppedOnBank = elementAtDrop ? group.bank.contains(elementAtDrop) : false;

            if (input) {
                assignDragChoice(group, input, value);
            } else if (sourceInput && droppedOnBank) {
                clearDragChoice(group, sourceInput);
            }

            clearDragTargetHighlights(group);
            sourceElement?.classList.remove('is-dragging');
            ghost.remove();
            window.removeEventListener('pointermove', moveDrag);
            window.removeEventListener('pointerup', finishDrag);
            window.removeEventListener('pointercancel', cancelDrag);
        }

        function cancelDrag() {
            clearDragTargetHighlights(group);
            sourceElement?.classList.remove('is-dragging');
            ghost.remove();
            window.removeEventListener('pointermove', moveDrag);
            window.removeEventListener('pointerup', finishDrag);
            window.removeEventListener('pointercancel', cancelDrag);
        }

        function moveDrag(pointerEvent) {
            pointerEvent.preventDefault();
            updatePointerDragGhost(state, pointerEvent.clientX, pointerEvent.clientY);
        }

        window.addEventListener('pointermove', moveDrag);
        window.addEventListener('pointerup', finishDrag);
        window.addEventListener('pointercancel', cancelDrag);
    }

    function syncDragChoiceGroups() {
        dragChoiceGroups.forEach((group) => {
            const usedValues = new Set();

            group.inputs.forEach((input) => {
                const value = canonicalDragValue(group, input.value);
                if (value && input.value !== value) {
                    input.value = value;
                }
                if (value) {
                    usedValues.add(value.toLowerCase());
                }

                const target = group.targets.get(input.name);
                if (!target) {
                    return;
                }

                const chip = target.querySelector('.drag-assigned-chip');
                const placeholder = target.querySelector('.drag-target-placeholder');
                const removeButton = target.querySelector('.drag-choice-remove');
                const description = group.items.find((item) => valueEquals(item.value, value))?.description || '';

                target.classList.toggle('has-choice', Boolean(value));
                target.dataset.value = value || '';
                chip.textContent = value;
                chip.title = description;
                chip.draggable = Boolean(value);
                chip.hidden = !value;
                placeholder.hidden = Boolean(value);
                removeButton.hidden = !value;
            });

            group.items.forEach((item) => {
                const isUsed = usedValues.has(item.value.toLowerCase());
                item.element.hidden = !group.reusable && isUsed;
                item.element.classList.toggle('is-picked', group.pendingValue === item.value);
                item.element.classList.toggle('is-used', !group.reusable && isUsed);
            });
        });
    }

    function assignDragChoice(group, input, rawValue) {
        const value = canonicalDragValue(group, rawValue);
        if (!value || !group.items.some((item) => valueEquals(item.value, value))) {
            return;
        }

        if (!group.reusable) {
            group.inputs.forEach((otherInput) => {
                if (otherInput !== input && valueEquals(otherInput.value, value)) {
                    otherInput.value = '';
                }
            });
        }

        input.value = value;
        group.pendingValue = '';
        syncDragChoiceGroups();
        scheduleSave();
    }

    function clearDragChoice(group, input) {
        input.value = '';
        syncDragChoiceGroups();
        scheduleSave();
    }

    function prepareDragTextRow(row, blank) {
        if (row.tagName !== 'P' || row.querySelector('.drag-assignment-text')) {
            return;
        }

        const text = document.createElement('span');
        text.className = 'drag-assignment-text';

        while (row.firstChild && row.firstChild !== blank) {
            text.appendChild(row.firstChild);
        }

        row.insertBefore(text, blank);
    }

    function registerBlankDragAssignment(group, row, blank) {
        const input = blank ? blank.querySelector('input') : null;
        if (!blank || !input || group.inputs.includes(input)) {
            return;
        }

        const rowBlanks = Array.from(row.querySelectorAll('.ielts-blank'));
        if (rowBlanks.length <= 1) {
            prepareDragTextRow(row, blank);
            row.classList.add('is-drag-assignment');
        }

        blank.hidden = true;
        group.inputs.push(input);
        blank.insertAdjacentElement('afterend', createDragTarget(group, input));
    }

    function registerAnswerFieldDragAssignment(group, field) {
        const input = field.querySelector('input');
        if (!input || group.inputs.includes(input)) {
            return;
        }

        field.classList.add('is-drag-assignment');
        input.hidden = true;
        group.inputs.push(input);
        field.appendChild(createDragTarget(group, input));
    }

    function createDragTarget(group, input) {
        const target = document.createElement('div');
        target.className = 'drag-assignment-target';
        target.setAttribute('role', 'button');
        target.setAttribute('tabindex', '0');
        target.innerHTML = `
            <span class="drag-target-placeholder">Drop letter</span>
            <span class="drag-assigned-chip" draggable="false" hidden></span>
            <button type="button" class="drag-choice-remove" aria-label="Remove answer" hidden>&times;</button>
        `;

        const chip = target.querySelector('.drag-assigned-chip');
        const removeButton = target.querySelector('.drag-choice-remove');
        target.dataset.inputName = input.name;

        target.addEventListener('click', (event) => {
            if (completed || event.target.closest('.drag-choice-remove')) {
                return;
            }

            if (group.pendingValue) {
                assignDragChoice(group, input, group.pendingValue);
            }
        });

        target.addEventListener('keydown', (event) => {
            if (completed) {
                return;
            }

            if ((event.key === 'Enter' || event.key === ' ') && group.pendingValue) {
                event.preventDefault();
                assignDragChoice(group, input, group.pendingValue);
            }
            if ((event.key === 'Backspace' || event.key === 'Delete') && input.value) {
                event.preventDefault();
                clearDragChoice(group, input);
            }
        });

        target.addEventListener('dragover', (event) => {
            if (completed) {
                return;
            }

            const data = readDragData(event);
            if (!data || (data.groupId && data.groupId !== group.id)) {
                return;
            }

            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
            target.classList.add('is-drag-over');
        });

        target.addEventListener('dragleave', () => {
            target.classList.remove('is-drag-over');
        });

        target.addEventListener('drop', (event) => {
            if (completed) {
                return;
            }

            const data = readDragData(event);
            if (!data || (data.groupId && data.groupId !== group.id)) {
                return;
            }

            event.preventDefault();
            target.classList.remove('is-drag-over');
            assignDragChoice(group, input, data.value);
        });

        chip.addEventListener('dragstart', (event) => {
            if (completed || !input.value) {
                event.preventDefault();
                return;
            }

            setDragData(event, group, input.value, input);
        });

        chip.addEventListener('pointerdown', (event) => {
            if (input.value) {
                startPointerDrag(event, group, input.value, input, chip);
            }
        });

        removeButton.addEventListener('click', () => {
            if (!completed) {
                clearDragChoice(group, input);
            }
        });

        group.targets.set(input.name, target);
        return target;
    }

    function setupDragChoiceAssignments() {
        const bankCandidates = Array.from(form.querySelectorAll(
            '.ielts-choice-box, .scientist-box, .ielts-note-box'
        ));

        bankCandidates.forEach((bank, index) => {
            const items = extractChoiceBankItems(bank);
            if (items.length < 2 || bank.dataset.dragChoiceReady === 'true') {
                return;
            }

            const assignmentContainer = findAssignmentContainerForBank(bank, items);
            if (!assignmentContainer) {
                return;
            }

            const group = {
                id: `drag-choice-${index}`,
                bank,
                items,
                inputs: [],
                targets: new Map(),
                pendingValue: '',
                reusable: contextAllowsRepeatedChoices(bank, assignmentContainer),
            };

            bank.dataset.dragChoiceReady = 'true';
            bank.classList.add('drag-choice-bank');
            if (group.reusable) {
                bank.classList.add('is-reusable');
            }

            items.forEach((item) => {
                item.element.classList.add('drag-choice-item');
                item.element.dataset.value = item.value;
                item.element.draggable = true;
                item.element.tabIndex = 0;
                item.element.setAttribute('role', 'button');
                item.element.title = item.description
                    ? `${item.value} - ${item.description}`
                    : item.value;

                item.element.addEventListener('keydown', (event) => {
                    if (completed || item.element.hidden) {
                        return;
                    }

                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        group.pendingValue = group.pendingValue === item.value ? '' : item.value;
                        syncDragChoiceGroups();
                    }
                });

                item.element.addEventListener('dragstart', (event) => {
                    if (completed || item.element.hidden) {
                        event.preventDefault();
                        return;
                    }

                    setDragData(event, group, item.value);
                    item.element.classList.add('is-dragging');
                });

                item.element.addEventListener('dragend', () => {
                    item.element.classList.remove('is-dragging');
                });

                item.element.addEventListener('pointerdown', (event) => {
                    startPointerDrag(event, group, item.value, null, item.element);
                });
            });

            bank.addEventListener('dragover', (event) => {
                const data = readDragData(event);
                if (!data || data.groupId !== group.id || !data.sourceName) {
                    return;
                }

                event.preventDefault();
                event.dataTransfer.dropEffect = 'move';
            });

            bank.addEventListener('drop', (event) => {
                const data = readDragData(event);
                if (!data || data.groupId !== group.id || !data.sourceName) {
                    return;
                }

                const input = group.inputs.find((candidate) => candidate.name === data.sourceName);
                if (input) {
                    event.preventDefault();
                    clearDragChoice(group, input);
                }
            });

            assignmentContainer.querySelectorAll('.mc-question').forEach((question) => {
                const compactOptions = question.querySelector('.mc-options.compact-options');
                const input = question.querySelector('input[type="hidden"]');
                if (!compactOptions || !input || !assignmentValuesMatchBank(question, items)) {
                    return;
                }

                question.classList.add('is-drag-assignment');
                compactOptions.hidden = true;
                group.inputs.push(input);
                compactOptions.insertAdjacentElement('beforebegin', createDragTarget(group, input));
            });

            assignmentContainer.querySelectorAll('label, p').forEach((label) => {
                label.querySelectorAll('.ielts-blank').forEach((blank) => {
                    registerBlankDragAssignment(group, label, blank);
                });
            });

            assignmentContainer.querySelectorAll('.answer-field').forEach((field) => {
                registerAnswerFieldDragAssignment(group, field);
            });

            if (group.inputs.length) {
                dragChoiceGroups.push(group);
            } else {
                bank.classList.remove('drag-choice-bank', 'is-reusable');
                bank.dataset.dragChoiceReady = '';
            }
        });

        syncDragChoiceGroups();
    }

    function setupHighlighter() {
        const highlightContainers = Array.from(document.querySelectorAll(
            '.reading-passages, .reading-questions, .ielts-paper'
        ));
        if (!highlightContainers.length) {
            return;
        }

        const palette = document.createElement('div');
        palette.className = 'highlight-palette';
        palette.hidden = true;
        ['yellow', 'green', 'blue'].forEach((color) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `highlight-choice highlight-${color}`;
            button.dataset.color = color;
            button.setAttribute('aria-label', `${color} highlight`);
            palette.appendChild(button);
        });
        document.body.appendChild(palette);

        function hidePalette() {
            palette.hidden = true;
        }

        function elementFromNode(node) {
            if (!node) {
                return null;
            }

            return node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
        }

        function containerForRange(range) {
            return highlightContainers.find((container) => (
                container.contains(range.startContainer)
                && container.contains(range.endContainer)
            ));
        }

        function selectedRangeInsidePractice() {
            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
                return null;
            }

            const range = selection.getRangeAt(0);
            const container = containerForRange(range);
            if (!container) {
                return null;
            }

            const anchorElement = elementFromNode(selection.anchorNode);
            const focusElement = elementFromNode(selection.focusNode);
            const blockedSelector = 'input, textarea, select, audio, video, script, style';
            if (
                (anchorElement && anchorElement.closest(blockedSelector))
                || (focusElement && focusElement.closest(blockedSelector))
            ) {
                return null;
            }

            return { range, container };
        }

        function showPalette() {
            const selectionInfo = selectedRangeInsidePractice();
            if (!selectionInfo) {
                hidePalette();
                return;
            }

            const { range } = selectionInfo;
            const rect = range.getBoundingClientRect();
            palette.style.left = `${Math.min(window.innerWidth - 130, rect.right + window.scrollX + 8)}px`;
            palette.style.top = `${Math.max(8, rect.top + window.scrollY - 42)}px`;
            palette.hidden = false;
        }

        function applyHighlight(color) {
            const selectionInfo = selectedRangeInsidePractice();
            if (!selectionInfo) {
                hidePalette();
                return;
            }

            const { range, container } = selectionInfo;
            if (!range.toString().trim()) {
                hidePalette();
                return;
            }

            const textNodes = [];
            const walker = document.createTreeWalker(
                container,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode(node) {
                        const parent = node.parentElement;
                        if (
                            !node.nodeValue.trim()
                            || !range.intersectsNode(node)
                            || (parent && parent.closest('input, textarea, select, audio, video, script, style'))
                        ) {
                            return NodeFilter.FILTER_REJECT;
                        }

                        return NodeFilter.FILTER_ACCEPT;
                    },
                }
            );

            let node = walker.nextNode();
            while (node) {
                textNodes.push(node);
                node = walker.nextNode();
            }

            textNodes.forEach((textNode) => {
                let startOffset = 0;
                let endOffset = textNode.nodeValue.length;

                if (textNode === range.startContainer) {
                    startOffset = range.startOffset;
                }
                if (textNode === range.endContainer) {
                    endOffset = range.endOffset;
                }
                if (startOffset >= endOffset) {
                    return;
                }

                const nodeRange = document.createRange();
                nodeRange.setStart(textNode, startOffset);
                nodeRange.setEnd(textNode, endOffset);

                const mark = document.createElement('mark');
                mark.className = `reader-highlight reader-highlight-${color}`;
                nodeRange.surroundContents(mark);
                nodeRange.detach();
            });

            if (typeof range.detach === 'function') {
                range.detach();
            }
            window.getSelection().removeAllRanges();
            hidePalette();
        }

        highlightContainers.forEach((container) => {
            container.addEventListener('mouseup', () => window.setTimeout(showPalette, 0));
            container.addEventListener('keyup', showPalette);
        });
        palette.addEventListener('mousedown', (event) => event.preventDefault());
        palette.addEventListener('click', (event) => {
            const button = event.target.closest('button[data-color]');
            if (button) {
                applyHighlight(button.dataset.color);
            }
        });
        document.addEventListener('mousedown', (event) => {
            if (
                !palette.contains(event.target)
                && !highlightContainers.some((container) => container.contains(event.target))
            ) {
                hidePalette();
            }
        });
    }

    function setupLockedAudio() {
        if (!audio) {
            return;
        }

        audio.controls = false;
        audio.removeAttribute('controls');
        audio.autoplay = true;
        audio.setAttribute('playsinline', '');

        let lastAllowedTime = 0;
        let restoringPosition = false;
        let waitingForGesture = false;

        function startAudio() {
            if (completed || audio.ended) {
                return;
            }

            const playAttempt = audio.play();
            if (playAttempt && typeof playAttempt.then === 'function') {
                playAttempt.then(() => {
                    waitingForGesture = false;
                }).catch(() => {
                    if (waitingForGesture) {
                        return;
                    }

                    waitingForGesture = true;
                    const startAfterGesture = () => startAudio();
                    document.addEventListener('click', startAfterGesture, { once: true });
                    document.addEventListener('keydown', startAfterGesture, { once: true });
                });
            }
        }

        audio.addEventListener('timeupdate', () => {
            if (!audio.seeking) {
                lastAllowedTime = audio.currentTime;
            }
        });

        audio.addEventListener('seeking', () => {
            if (restoringPosition || completed) {
                return;
            }

            if (Math.abs(audio.currentTime - lastAllowedTime) > 0.75) {
                restoringPosition = true;
                audio.currentTime = lastAllowedTime;
                window.setTimeout(() => {
                    restoringPosition = false;
                }, 0);
            }
        });

        audio.addEventListener('pause', () => {
            if (!completed && !audio.ended) {
                window.setTimeout(startAudio, 0);
            }
        });

        audio.addEventListener('ratechange', () => {
            if (audio.playbackRate !== 1) {
                audio.playbackRate = 1;
            }
        });

        startAudio();
    }

    function updateStorage() {
        // Attempts intentionally do not persist in-progress timing or answers.
        // Re-entering a test should always start a fresh paper.
    }

    function updateTimers() {
        if (timerDisplay) {
            if (isListening) {
                timerDisplay.hidden = !Number.isFinite(reviewRemaining);
                timerDisplay.textContent = Number.isFinite(reviewRemaining)
                    ? formatTime(Math.max(reviewRemaining, 0))
                    : '';
                timerDisplay.classList.toggle('danger', Number.isFinite(reviewRemaining) && reviewRemaining <= 60);
            } else {
                timerDisplay.hidden = false;
                timerDisplay.textContent = formatTime(Math.max(remaining, 0));
                timerDisplay.classList.toggle('danger', remaining <= 300);
            }
        }

        if (reviewTimer && Number.isFinite(reviewRemaining)) {
            reviewTimer.textContent = formatTime(Math.max(reviewRemaining, 0));
        }

        if (reviewBanner && Number.isFinite(reviewRemaining) && !completed) {
            reviewBanner.hidden = false;
        }
    }

    async function savePractice(status = 'in_progress') {
        if (status !== 'completed') {
            if (saveStatus) {
                saveStatus.textContent = isPreview ? 'Preview' : 'Not submitted';
            }
            return;
        }

        if (saveInFlight) {
            return;
        }

        saveInFlight = true;
        if (saveStatus) {
            saveStatus.textContent = status === 'completed' ? 'Submitting' : 'Saving';
        }

        const payload = {
            book_number: bookNumber,
            test_number: testNumber,
            section,
            answers: collectAnswers(),
            status,
            time_remaining_seconds: Math.max(remaining, 0),
            review_remaining_seconds: Number.isFinite(reviewRemaining)
                ? Math.max(reviewRemaining, 0)
                : null,
        };

        try {
            const response = await fetch(saveUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error('Save failed');
            }

            const data = await response.json();
            if (saveStatus) {
                if (status === 'completed' && data.score !== null) {
                    const bandText = data.band_score !== null && data.band_score !== undefined
                        ? ` | Band ${data.band_score}`
                        : '';
                    saveStatus.textContent = `Completed: ${data.score}/${data.total_questions}${bandText}`;
                } else {
                    saveStatus.textContent = status === 'completed' ? 'Completed' : 'Saved';
                }
            }

            if (status === 'completed' && data.score !== null) {
                showResult(data.score, data.total_questions, data.band_score);
                applyResultDetails(data.details || {});
            }
        } catch (error) {
            if (saveStatus) {
                saveStatus.textContent = isPreview ? 'Could not score' : 'Not saved';
            }
        } finally {
            saveInFlight = false;
        }
    }

    function scheduleSave() {
        if (completed) {
            return;
        }

        updateFilledBlanks();
        updateMultipleChoice();
        updateMultiAnswerChoices();

        if (saveTimeout) {
            window.clearTimeout(saveTimeout);
        }

        if (saveStatus) {
            saveStatus.textContent = isPreview ? 'Preview' : 'Not submitted';
        }

        saveTimeout = window.setTimeout(() => updateStorage(), 700);
    }

    function setupExitWarning() {
        const modal = document.createElement('div');
        modal.className = 'exit-warning-modal';
        modal.hidden = true;
        modal.innerHTML = `
            <div class="exit-warning-dialog" role="dialog" aria-modal="true" aria-labelledby="exitWarningTitle">
                <h2 id="exitWarningTitle">Leave this test?</h2>
                <p>Your result won't be saved if you exit. Submit your unfinished test instead.</p>
                <div class="exit-warning-actions">
                    <button type="button" class="button secondary" data-exit-stay>Stay</button>
                    <button type="button" class="button primary" data-exit-anyway>Exit anyway</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        let pendingUrl = null;

        function hideModal() {
            modal.hidden = true;
            pendingUrl = null;
        }

        function showModal(url) {
            pendingUrl = url;
            modal.hidden = false;
            const stayButton = modal.querySelector('[data-exit-stay]');
            if (stayButton) {
                stayButton.focus();
            }
        }

        modal.querySelector('[data-exit-stay]').addEventListener('click', hideModal);
        modal.querySelector('[data-exit-anyway]').addEventListener('click', () => {
            allowNavigation = true;
            if (pendingUrl) {
                window.location.href = pendingUrl;
            }
        });

        document.addEventListener('click', (event) => {
            const link = event.target.closest('a[href]');
            if (!link || completed || allowNavigation) {
                return;
            }

            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || link.target === '_blank') {
                return;
            }

            const url = new URL(link.href, window.location.href);
            const currentUrl = new URL(window.location.href);
            if (url.href === currentUrl.href) {
                return;
            }

            event.preventDefault();
            showModal(url.href);
        });

        window.addEventListener('beforeunload', (event) => {
            if (completed || allowNavigation) {
                return;
            }

            event.preventDefault();
            event.returnValue = '';
        });
    }

    async function completePractice() {
        if (completed) {
            return;
        }

        completed = true;
        remaining = 0;
        reviewRemaining = null;
        updateTimers();
        await savePractice('completed');
        lockCompletedForm();
    }

    function initialResultDetails() {
        const detailsElement = document.querySelector('#resultDetails');
        if (!detailsElement) {
            return {};
        }

        try {
            return JSON.parse(detailsElement.textContent || '{}');
        } catch (error) {
            return {};
        }
    }

    function lockCompletedForm() {
        form.querySelectorAll(
            'input, button[type="submit"], .mc-option, .multi-option, .drag-choice-remove'
        ).forEach((element) => {
            element.disabled = true;
        });
    }

    form.addEventListener('input', (event) => {
        normalizeAnswerInput(event.target);
        scheduleSave();
    });
    form.querySelectorAll('.mc-option').forEach((button) => {
        button.addEventListener('click', () => {
            if (completed || button.disabled) {
                return;
            }

            const group = button.closest('.mc-question');
            const input = group.querySelector('input[type="hidden"]');
            input.value = button.dataset.value;
            updateMultipleChoice();
            scheduleSave();
        });
    });

    form.querySelectorAll('.multi-option').forEach((button) => {
        button.addEventListener('click', () => {
            if (completed || button.disabled) {
                return;
            }

            const group = button.closest('.multi-answer-question');
            const inputs = Array.from(group.querySelectorAll('input[type="hidden"]'));
            let selected = inputs.map((input) => input.value.trim().toUpperCase()).filter(Boolean);
            const value = button.dataset.value;

            if (selected.includes(value)) {
                selected = selected.filter((item) => item !== value);
            } else if (selected.length < inputs.length) {
                selected.push(value);
            } else {
                selected[selected.length - 1] = value;
            }

            inputs.forEach((input, index) => {
                input.value = selected[index] || '';
            });
            updateMultiAnswerChoices();
            scheduleSave();
        });
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        await completePractice();
    });

    if (audio) {
        setupLockedAudio();
        audio.addEventListener('ended', () => {
            if (!completed && !Number.isFinite(reviewRemaining)) {
                reviewRemaining = Number(shell.dataset.reviewSeconds || 120);
                updateTimers();
            }
        });
    }

    setupDragChoiceAssignments();
    normalizeAllAnswerInputs();
    updateFilledBlanks();
    updateMultipleChoice();
    updateMultiAnswerChoices();
    updateTimers();
    setupHighlighter();
    setupExitWarning();

    if (completed) {
        if (saveStatus) {
            saveStatus.textContent = completedStatusText(existingScore, 40, existingBand);
        }
        showResult(existingScore, 40, existingBand);
        applyResultDetails(initialResultDetails());
        lockCompletedForm();
    }

    window.setInterval(() => {
        if (completed) {
            return;
        }

        if (isReading) {
            remaining -= 1;
        }

        if (Number.isFinite(reviewRemaining)) {
            reviewRemaining -= 1;
            if (reviewRemaining <= 0) {
                completePractice();
                return;
            }
        }

        if (isReading && remaining <= 0) {
            completePractice();
            return;
        }

        updateTimers();
        updateStorage();
    }, 1000);

    window.setInterval(() => {
        updateStorage();
    }, 10000);
});
