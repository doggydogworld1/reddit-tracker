const toast = (message, kind = "success") => {
  const element = document.querySelector("#toast");
  if (!element) return;
  element.textContent = message;
  element.className = `toast visible ${kind}`;
  window.setTimeout(() => element.classList.remove("visible"), 4200);
};

document.querySelectorAll(".job-trigger").forEach((button) => {
  button.addEventListener("click", async () => {
    const job = button.dataset.job;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Queuing…";
    try {
      const response = await fetch(`/api/jobs/${job}`, { method: "POST" });
      if (!response.ok) throw new Error("Could not queue job");
      toast(`${job[0].toUpperCase() + job.slice(1)} job queued`);
      button.textContent = "Queued";
    } catch (error) {
      toast(error.message, "error");
      button.textContent = original;
    } finally {
      window.setTimeout(() => { button.disabled = false; button.textContent = original; }, 1800);
    }
  });
});

const form = document.querySelector("#configuration-form");
if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type='submit']");
    const result = document.querySelector("#save-result");
    const raw = Object.fromEntries(new FormData(form).entries());
    const numberFields = [
      "default_horizon_days", "discovery_post_limit", "author_history_limit",
      "min_post_chars", "track_score_threshold", "track_min_mature_claims",
      "winner_search_limit", "weekly_discovery_hour_utc", "daily_monitor_hour_utc"
    ];
    numberFields.forEach((field) => { raw[field] = Number(raw[field]); });
    raw.enable_ai_extraction = form.elements.enable_ai_extraction.checked;
    submit.disabled = true;
    submit.textContent = "Saving…";
    result.textContent = "";
    try {
      const response = await fetch("/api/configuration", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(raw),
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item) => item.msg).join(", ")
          : payload.detail || "Configuration rejected";
        throw new Error(detail);
      }
      result.textContent = "Saved. New credentials and scan settings apply to the next job.";
      result.className = "save-result success";
      toast("Configuration saved");
      window.setTimeout(() => window.location.reload(), 900);
    } catch (error) {
      result.textContent = error.message;
      result.className = "save-result error";
      toast(error.message, "error");
    } finally {
      submit.disabled = false;
      submit.textContent = "Save configuration";
    }
  });
}
