(() => {
  const contractVersion = "2026-03-03.v1";

  function requireModules(names, context) {
    const required = Array.isArray(names) ? names : [];
    const missing = required.filter((name) => !(name && window[name]));
    if (missing.length > 0) {
      const where = context ? ` for ${context}` : "";
      throw new Error(`Bootstrap contract ${contractVersion}${where} missing modules: ${missing.join(", ")}`);
    }
  }

  window.GRWBootstrapContract = {
    contract_version: contractVersion,
    requireModules,
  };
})();
