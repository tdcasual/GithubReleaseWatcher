(function attachSettingsController(global) {
  function createSettingsController(deps) {
    const getEl = deps.getEl;
    const normalizeAssetType = deps.normalizeAssetType;

    const validateIntField = ({ inputId, label, min, max, emptyOk }) => {
      const el = getEl(inputId);
      const raw = String(el?.value || "").trim();
      if (!raw) {
        if (emptyOk) return null;
        throw new Error(`${label}不能为空。`);
      }
      const num = Number(raw);
      if (!Number.isFinite(num) || !Number.isInteger(num)) throw new Error(`${label}必须为整数。`);
      if (min != null && num < min) throw new Error(`${label}必须 ≥ ${min}。`);
      if (max != null && num > max) throw new Error(`${label}必须 ≤ ${max}。`);
      return num;
    };

    const validateNumberField = ({ inputId, label, min, max, emptyOk }) => {
      const el = getEl(inputId);
      const raw = String(el?.value || "").trim();
      if (!raw) {
        if (emptyOk) return null;
        throw new Error(`${label}不能为空。`);
      }
      const num = Number(raw);
      if (!Number.isFinite(num)) throw new Error(`${label}必须为数字。`);
      if (min != null && num < min) throw new Error(`${label}必须 ≥ ${min}。`);
      if (max != null && num > max) throw new Error(`${label}必须 ≤ ${max}。`);
      return num;
    };

    const normalizeRepoPatch = (key, patch) => {
      const normalized = { ...patch };
      if ("keep_last" in normalized) {
        const raw = normalized.keep_last;
        if (raw === null || raw === undefined || raw === "") normalized.keep_last = null;
        else {
          const num = Number(raw);
          if (!Number.isFinite(num) || !Number.isInteger(num) || num < 1 || num > 1000) {
            throw new Error(`仓库 ${key} 的保留数量必须为 1~1000 或留空。`);
          }
          normalized.keep_last = num;
        }
      }
      if ("asset_types" in normalized) {
        const list = Array.isArray(normalized.asset_types) ? normalized.asset_types : [];
        const out = [];
        for (const item of list) {
          const norm = normalizeAssetType(item);
          if (!out.includes(norm)) out.push(norm);
        }
        normalized.asset_types = out;
      }
      return normalized;
    };

    return {
      normalizeRepoPatch,
      validateIntField,
      validateNumberField,
    };
  }

  global.GRWSettingsController = { createSettingsController };
})(window);
