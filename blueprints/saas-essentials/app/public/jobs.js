async function refreshJobs() {
  try {
    const response = await fetch("/api/jobs", { credentials: "same-origin" });
    if (!response.ok) return;
    const jobs = await response.json();
    const items = jobs.map((job) => {
      const item = document.createElement("li");
      item.textContent = `${job.kind}: ${job.state}${job.result?.category ? ` · ${job.result.category}` : ""}${job.kind === "summary" && job.result ? ` · ${job.result.completed}/${job.result.total} completed` : ""}`;
      return item;
    });
    document.getElementById("processing").replaceChildren(...items);
  } catch { /* The next poll can recover without exposing private errors. */ }
}
refreshJobs();
setInterval(refreshJobs, 10000);
