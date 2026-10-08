document.addEventListener("DOMContentLoaded", () => {
  const table = document.getElementById("progressTable");
  const searchInput = document.getElementById("searchInput");
  const jobIdFilter = document.getElementById("jobIdFilter");
  const stateFilter = document.getElementById("stateFilter");
  const projectFilter = document.getElementById("projectFilter");
  const assigneeFilter = document.getElementById("assigneeFilter");
  const downloadCsvButton = document.getElementById("downloadCsvButton");
  const visibleCount = document.getElementById("visibleCount");

  const autosaveInputs = Array.from(
    document.querySelectorAll(".autosave-input")
  );
  const saveAllButton = document.getElementById("saveAllButton");
  const saveStatus = document.getElementById("saveStatus");

  const dirtyInputs = new Set();
  const savingRequests = new Map();

  // Запоминаем последнее подтверждённое сервером значение каждого поля.
  autosaveInputs.forEach((input) => {
    input.dataset.savedValue = input.value;
  });

  // ------------------------------------
  // Отображение имени выбранного файла
  // ------------------------------------

  document.querySelectorAll(".file-picker input[type='file']").forEach((input) => {
    input.addEventListener("change", () => {
      const fileName = input
        .closest(".file-picker")
        ?.querySelector(".file-name");

      if (fileName) {
        fileName.textContent = input.files?.[0]?.name || "Файл не выбран";
      }
    });
  });

  // ------------------------------------
  // Фильтры таблицы
  // ------------------------------------

  function getDataRows() {
    if (!table) {
      return [];
    }

    return Array.from(
      table.querySelectorAll("tbody tr:not(.empty-row)")
    );
  }

  function fillMultiFilter(filter, values) {
    if (!filter) {
      return;
    }

    const uniqueValues = [
      ...new Set(
        values
          .map((value) => value.trim())
          .filter(Boolean)
      )
    ].sort((a, b) => a.localeCompare(b, "ru"));

    const options = filter.querySelector(".multi-filter__options");

    uniqueValues.forEach((value) => {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      const text = document.createElement("span");

      checkbox.type = "checkbox";
      checkbox.value = value;
      text.textContent = value;
      label.append(checkbox, text);
      options?.appendChild(label);
    });
  }

  function getSelectedValues(filter) {
    return new Set(
      Array.from(filter?.querySelectorAll('input[type="checkbox"]:checked') || [])
        .map((checkbox) => checkbox.value)
    );
  }

  function updateFilterLabel(filter) {
    if (!filter) {
      return;
    }

    const selected = [...getSelectedValues(filter)];
    const label = filter.querySelector("summary span");

    if (label) {
      label.textContent = selected.length === 0
        ? filter.dataset.placeholder
        : selected.length === 1
          ? selected[0]
          : `Выбрано: ${selected.length}`;
    }
  }

  const rows = getDataRows();

  fillMultiFilter(
    stateFilter,
    rows.map((row) => row.dataset.state || "")
  );

  fillMultiFilter(
    projectFilter,
    rows.map((row) => row.dataset.project || "")
  );

  fillMultiFilter(
    assigneeFilter,
    rows.map((row) => row.dataset.assignee || "")
  );

  function applyFilters() {
    const query = (searchInput?.value || "").trim().toLowerCase();
    const jobIds = new Set(
      (jobIdFilter?.value || "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean)
    );
    const states = getSelectedValues(stateFilter);
    const projects = getSelectedValues(projectFilter);
    const assignees = getSelectedValues(assigneeFilter);

    let count = 0;

    rows.forEach((row) => {
      const matchesSearch =
        !query || row.textContent.toLowerCase().includes(query);

      const matchesJobId =
        jobIds.size === 0 || jobIds.has((row.dataset.jobId || "").trim());

      const matchesState =
        states.size === 0 || states.has(row.dataset.state || "");

      const matchesProject =
        projects.size === 0 || projects.has(row.dataset.project || "");

      const matchesAssignee =
        assignees.size === 0 || assignees.has(row.dataset.assignee || "");

      const visible =
        matchesSearch &&
        matchesJobId &&
        matchesState &&
        matchesProject &&
        matchesAssignee;

      row.hidden = !visible;

      if (visible) {
        count += 1;
      }
    });

    if (visibleCount) {
      visibleCount.textContent = String(count);
    }
  }

  searchInput?.addEventListener("input", applyFilters);
  jobIdFilter?.addEventListener("input", applyFilters);
  [stateFilter, projectFilter, assigneeFilter].forEach((filter) => {
    filter?.addEventListener("change", () => {
      updateFilterLabel(filter);
      applyFilters();
    });

    filter?.addEventListener("toggle", () => {
      if (!filter.open) {
        return;
      }

      [stateFilter, projectFilter, assigneeFilter]
        .filter((otherFilter) => otherFilter && otherFilter !== filter)
        .forEach((otherFilter) => {
          otherFilter.open = false;
        });
    });
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".multi-filter")) {
      return;
    }

    [stateFilter, projectFilter, assigneeFilter]
      .filter(Boolean)
      .forEach((filter) => {
        filter.open = false;
      });
  });

  // ------------------------------------
  // Экспорт текущего представления таблицы в CSV
  // ------------------------------------

  function getCellValue(cell) {
    const input = cell.querySelector("input, select, textarea");
    return input ? input.value : cell.textContent.trim();
  }

  function escapeCsvValue(value) {
    return `"${String(value).replaceAll('"', '""')}"`;
  }

  downloadCsvButton?.addEventListener("click", () => {
    const headers = Array.from(table?.querySelectorAll("thead th") || [])
      .slice(0, -1)
      .map((header) => header.textContent.trim());
    const visibleRows = rows.filter((row) => !row.hidden);

    const csvRows = [
      headers,
      ...visibleRows.map((row) =>
        Array.from(row.cells)
          .slice(0, -1)
          .map(getCellValue)
      )
    ];

    const csv = "\uFEFF" + csvRows
      .map((values) => values.map(escapeCsvValue).join(";"))
      .join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const date = new Date().toISOString().slice(0, 10);

    link.href = url;
    link.download = `cvat-progress-${date}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });

  // ------------------------------------
  // Состояние ручного редактирования
  // ------------------------------------

  function updateSaveBar() {
    if (!saveAllButton || !saveStatus) {
      return;
    }

    if (dirtyInputs.size === 0) {
      saveAllButton.disabled = true;
      saveStatus.textContent = "Все изменения сохранены";
      return;
    }

    saveAllButton.disabled = false;
    saveStatus.textContent = `Несохранённых изменений: ${dirtyInputs.size}`;
  }

  function syncDirtyState(input) {
    const savedValue = input.dataset.savedValue ?? "";

    if (input.value === savedValue) {
      dirtyInputs.delete(input);
      input.classList.remove("input--dirty");
      input.classList.remove("input--error");
    } else {
      dirtyInputs.add(input);
      input.classList.add("input--dirty");
      input.classList.remove("input--saved");
      input.classList.remove("input--error");
    }

    updateSaveBar();
  }

  function showSaved(input) {
    input.classList.remove("input--saving");
    input.classList.remove("input--error");

    if (!dirtyInputs.has(input)) {
      input.classList.remove("input--dirty");
      input.classList.add("input--saved");

      window.setTimeout(() => {
        input.classList.remove("input--saved");
      }, 900);
    }
  }

  function showError(input, message = "Не удалось сохранить изменения") {
    input.classList.remove("input--saving");
    input.classList.add("input--error");

    if (saveStatus) {
      saveStatus.textContent = message;
    }

    if (saveAllButton) {
      saveAllButton.disabled = false;
    }
  }

  // ------------------------------------
  // Сохранение одного ручного поля
  // ------------------------------------

  function saveInput(input) {
    if (!dirtyInputs.has(input)) {
      return Promise.resolve(true);
    }

    // Если это поле уже сохраняется, повторный запрос не запускаем.
    // Кнопка "Сохранить" дождётся того же запроса.
    const existingRequest = savingRequests.get(input);
    if (existingRequest) {
      return existingRequest;
    }

    const valueAtStart = input.value;
    const rowId = Number(input.dataset.rowId);
    const field = input.dataset.field;

    if (!Number.isInteger(rowId) || rowId <= 0 || !field) {
      showError(input, "Ошибка данных строки");
      return Promise.resolve(false);
    }

    input.classList.add("input--saving");
    input.classList.remove("input--error");

    const request = fetch("/api/rows/update", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        row_id: rowId,
        field: field,
        value: valueAtStart
      })
    })
      .then(async (response) => {
        if (!response.ok) {
          let detail = `HTTP ${response.status}`;

          try {
            const data = await response.json();
            detail = data.detail || detail;
          } catch (_) {
            // Ответ мог быть не JSON.
          }

          throw new Error(detail);
        }

        // Сервер подтвердил именно valueAtStart.
        input.dataset.savedValue = valueAtStart;

        // Если пользователь успел изменить поле, новое значение остаётся dirty.
        syncDirtyState(input);
        showSaved(input);

        return true;
      })
      .catch((error) => {
        console.error("Ошибка сохранения поля:", error);
        showError(input);
        return false;
      })
      .finally(() => {
        savingRequests.delete(input);
      });

    savingRequests.set(input, request);
    return request;
  }

  // ------------------------------------
  // Ручной ввод + сохранение только по blur
  // ------------------------------------

  autosaveInputs.forEach((input) => {
    input.addEventListener("input", () => {
      syncDirtyState(input);

      if (input.dataset.field === "visual") {
        applyFilters();
      }
    });

    input.addEventListener("blur", () => {
      void saveInput(input);
    });
  });

  // ------------------------------------
  // Общая кнопка "Сохранить"
  // ------------------------------------

  saveAllButton?.addEventListener("click", async () => {
    if (dirtyInputs.size === 0) {
      return;
    }

    const inputsToSave = [...dirtyInputs];

    saveAllButton.disabled = true;

    if (saveStatus) {
      saveStatus.textContent = "Сохранение...";
    }

    const results = await Promise.all(
      inputsToSave.map((input) => saveInput(input))
    );

    const allSaved = results.every(Boolean) && dirtyInputs.size === 0;

    if (allSaved) {
      if (saveStatus) {
        saveStatus.textContent = "Все изменения сохранены";
      }

      saveAllButton.disabled = true;
    } else {
      updateSaveBar();

      if (saveStatus && dirtyInputs.size > 0) {
        saveStatus.textContent = "Не все изменения удалось сохранить";
      }
    }
  });

  // ------------------------------------
  // Защита от закрытия с несохранёнными данными
  // ------------------------------------

  window.addEventListener("beforeunload", (event) => {
    if (dirtyInputs.size === 0) {
      return;
    }

    event.preventDefault();
    event.returnValue = "";
  });

  updateSaveBar();
});
