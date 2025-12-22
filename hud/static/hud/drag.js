(() => {
    const csrfToken = window.hudConfig?.csrfToken;
    const itemPool = document.getElementById('item-pool');
    const display = document.getElementById('selected-display');

    if (!itemPool || !csrfToken) {
        return;
    }

    itemPool.querySelectorAll('.item-chip').forEach((chip) => {
        chip.setAttribute('draggable', 'true');
            chip.addEventListener('dragstart', (event) => {
                event.dataTransfer?.setData('text/plain', chip.dataset.itemId || '');
                if (chip.dataset.itemImage) {
                    event.dataTransfer?.setData('text/image', chip.dataset.itemImage);
                }
                chip.classList.add('dragging');
            });
        chip.addEventListener('dragend', () => chip.classList.remove('dragging'));
    });

    document.querySelectorAll('.inventory-slot').forEach((slot) => {
        slot.addEventListener('dragover', (event) => {
            event.preventDefault();
            slot.classList.add('drag-over');
        });

        slot.addEventListener('dragleave', () => {
            slot.classList.remove('drag-over');
        });

        slot.addEventListener('drop', (event) => {
            event.preventDefault();
            slot.classList.remove('drag-over');
            const itemId = event.dataTransfer?.getData('text/plain');
            if (!itemId) return;
            assignSlot(slot, itemId);
        });

        slot.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            assignSlot(slot, '');
        });
    });

    function assignSlot(slot, itemId) {
        const url = slot.dataset.assignUrl;
        if (!url) return;

        const payload = new URLSearchParams();
        if (itemId) {
            payload.append('item_id', itemId);
        }

        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: payload,
        })
            .then((response) => response.json())
            .then((data) => {
                    slot.dataset.itemName = data.itemName;
                    slot.dataset.itemImage = data.itemImage || '';

                    const figure = slot.querySelector('.slot-figure');
                    if (figure) {
                        if (data.itemImage) {
                            figure.classList.remove('empty');
                            figure.style.backgroundImage = `url('${data.itemImage}')`;
                        } else {
                            figure.classList.add('empty');
                            figure.style.backgroundImage = '';
                        }
                    }

                    const selectedFigure = document.getElementById('selected-figure');
                    const selectedName = document.getElementById('selected-name');
                    if (selectedName) {
                        selectedName.textContent = data.itemName;
                    }
                    if (selectedFigure) {
                        if (data.itemImage) {
                            selectedFigure.classList.remove('empty');
                            selectedFigure.style.backgroundImage = `url('${data.itemImage}')`;
                        } else {
                            selectedFigure.classList.add('empty');
                            selectedFigure.style.backgroundImage = '';
                        }
                    }
            })
            .catch(() => {
                // Intentionally silent to keep UI minimal; consider surface message if needed.
            });
    }
})();
