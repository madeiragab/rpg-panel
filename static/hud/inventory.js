(() => {
  const csrfToken = window.hudConfig?.csrfToken;
  const addBtn = document.getElementById('add-item-btn');
  const picker = document.getElementById('item-picker');
  const itemPool = document.getElementById('item-pool');
  const grid = document.getElementById('inventory-grid');
  const selectedFigure = document.getElementById('selected-figure');
  const selectedName = document.getElementById('selected-name');

  if (!grid || !csrfToken) return;

  // Toggle item picker
  if (addBtn && picker) {
    addBtn.addEventListener('click', () => {
      picker.style.display = picker.style.display === 'none' ? 'block' : 'none';
    });
  }

  // Assign to first empty slot when clicking an item
  if (itemPool) {
    itemPool.querySelectorAll('.item-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const itemId = chip.dataset.itemId;
        if (!itemId) return;
        const emptySlot = findFirstEmptySlot();
        if (!emptySlot) {
          // No empty slot; collapse picker
          if (picker) picker.style.display = 'none';
          return;
        }
        assignSlot(emptySlot, itemId);
        if (picker) picker.style.display = 'none';
      });
    });
  }

  // Click a slot to remove item
  grid.querySelectorAll('.inventory-slot').forEach((slot) => {
    slot.addEventListener('click', () => {
      // If slot has item, remove it
      const hasItem = !!slot.dataset.itemImage || (slot.dataset.itemName && slot.dataset.itemName !== 'Vazio');
      if (hasItem) {
        assignSlot(slot, '');
      } else {
        // Update selected display to show empty
        updateSelected('', '');
      }
    });
  });

  function findFirstEmptySlot() {
    const slots = Array.from(grid.querySelectorAll('.inventory-slot'));
    return slots.find((slot) => {
      const img = slot.dataset.itemImage;
      const name = slot.dataset.itemName;
      return !img && (!name || name === 'Vazio');
    });
  }

  function assignSlot(slot, itemId) {
    const url = slot.dataset.assignUrl;
    if (!url) return;

    const payload = new URLSearchParams();
    if (itemId) payload.append('item_id', itemId);

    fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: payload,
    })
      .then((r) => r.json())
      .then((data) => {
        // Update slot dataset
        slot.dataset.itemName = data.itemName || 'Vazio';
        slot.dataset.itemImage = data.itemImage || '';

        // Update slot UI
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

        // Update selected display
        updateSelected(data.itemImage || '', data.itemName || 'Vazio');
      })
      .catch(() => {});
  }

  function updateSelected(img, name) {
    if (selectedName) selectedName.textContent = name || 'Vazio';
    if (selectedFigure) {
      if (img) {
        selectedFigure.classList.remove('empty');
        selectedFigure.style.backgroundImage = `url('${img}')`;
      } else {
        selectedFigure.classList.add('empty');
        selectedFigure.style.backgroundImage = '';
      }
    }
  }
})();
