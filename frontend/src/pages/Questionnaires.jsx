import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { quizApi } from "../services/api.js";
import { PageShell } from "../components/quiz/QuestionInput.jsx";

const btn = "inline-flex min-h-11 items-center justify-center rounded-full px-4 text-sm disabled:opacity-40";

const STATUS = { not_started: "Not started", in_progress: "Saved, not submitted", submitted: "Submitted" };

export function QuestionnaireList() {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    quizApi
      .questionnaires()
      .then((d) => setList(d.questionnaires))
      .catch((e) => setError(e.message));
  }, []);
  return (
    <PageShell
      eyebrow="Your views"
      title="Questionnaires"
      actions={
        <Link to="/activities" className={`${btn} border border-rule bg-cream text-navy`}>
          Activities
        </Link>
      }
    >
      <p className="mb-4 max-w-2xl text-sm text-muted">
        These questions ask what you think. There are no right or wrong answers and they are not marked. You may skip any question.
      </p>
      {error ? <p className="text-sm text-red-700" role="alert">{error}</p> : null}
      {!list ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : list.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-rule p-4 text-sm text-muted">No questionnaires are open right now.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {list.map((q) => (
            <li key={q.id} className="flex min-w-0 flex-col rounded-3xl border border-rule bg-cream p-4">
              <h2 className="font-serif text-lg text-navy">{q.title}</h2>
              {q.description ? <p className="mt-1 text-sm text-muted">{q.description}</p> : null}
              <p className="mt-2 text-xs text-muted">
                {q.item_count} statements · {STATUS[q.my_status] || q.my_status}
                {!q.open ? " · closed" : ""}
              </p>
              <div className="mt-3">
                {q.my_status === "submitted" ? (
                  <span className="text-sm text-green-800">Thank you, submitted.</span>
                ) : q.open ? (
                  <Link to={`/questionnaires/${q.id}`} className={`${btn} bg-navy text-cream`}>
                    {q.my_status === "in_progress" ? "Continue" : "Start"}
                  </Link>
                ) : (
                  <span className="text-sm text-muted">Not open now.</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}

export function QuestionnairePlayer() {
  const { instrumentId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [values, setValues] = useState({});
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const dirty = useRef(false);

  useEffect(() => {
    quizApi
      .questionnaire(instrumentId)
      .then((d) => {
        setData(d);
        setValues(d.response.values || {});
      })
      .catch((e) => setError(e.message));
  }, [instrumentId]);

  useEffect(() => {
    const warn = (e) => {
      if (dirty.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const save = async (submit) => {
    setBusy(true);
    setError("");
    try {
      // Send every item: unanswered ones as null, so "skipped" is stored as missing, not zero.
      const answers = Object.fromEntries(data.items.map((i) => [i.id, values[i.id] ?? null]));
      await quizApi.saveQuestionnaire(instrumentId, answers, submit);
      dirty.current = false;
      if (submit) navigate("/questionnaires");
      else setSaved(`Saved at ${new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };

  if (error && !data) {
    return (
      <PageShell eyebrow="Questionnaire" title="Not available">
        <p className="text-sm text-red-700" role="alert">{error}</p>
        <Link to="/questionnaires" className={`${btn} mt-3 border border-navy text-navy`}>Back</Link>
      </PageShell>
    );
  }
  if (!data) return <p className="p-8 text-sm text-muted">Loading…</p>;
  const q = data.questionnaire;
  const points = [];
  for (let v = q.scale_min; v <= q.scale_max; v += 1) points.push(v);
  const labelFor = (v) => q.scale_labels?.[v - q.scale_min] || String(v);
  const answered = data.items.filter((i) => values[i.id] != null).length;
  const submitted = data.response.status === "submitted";

  return (
    <PageShell
      eyebrow="Questionnaire"
      title={q.title}
      actions={
        <Link to="/questionnaires" className={`${btn} border border-rule bg-cream text-navy`}>
          All questionnaires
        </Link>
      }
    >
      <p className="mb-2 max-w-2xl text-sm text-muted">
        Choose how much you agree with each statement. Skipping is allowed and is recorded as “not answered”.
      </p>
      <p className="mb-4 text-sm" aria-live="polite">
        {answered} of {data.items.length} answered{saved ? ` · ${saved}` : ""}
      </p>
      {submitted ? <p className="mb-4 rounded-2xl bg-green-50 p-3 text-sm text-green-900">You have already submitted this questionnaire.</p> : null}
      <ol className="space-y-3">
        {data.items.map((item, idx) => (
          <li key={item.id} className="min-w-0 rounded-3xl border border-rule bg-cream p-4">
            <fieldset disabled={submitted || !q.open}>
              <legend className="text-sm font-medium">
                {idx + 1}. {item.text}
              </legend>
              <div className="mt-3 grid grid-cols-1 gap-2 min-[480px]:grid-cols-5">
                {points.map((v) => (
                  <label
                    key={v}
                    className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-2xl border px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-navy ${
                      values[item.id] === v ? "border-navy bg-navy/10" : "border-rule bg-paper"
                    }`}
                  >
                    <input
                      type="radio"
                      className="h-4 w-4 accent-navy"
                      name={`item-${item.id}`}
                      checked={values[item.id] === v}
                      onChange={() => {
                        dirty.current = true;
                        setValues({ ...values, [item.id]: v });
                      }}
                    />
                    <span className="min-w-0 break-words">{labelFor(v)}</span>
                  </label>
                ))}
              </div>
              {values[item.id] != null && !submitted ? (
                <button
                  type="button"
                  className="mt-2 min-h-9 text-xs text-muted underline"
                  onClick={() => {
                    dirty.current = true;
                    setValues({ ...values, [item.id]: null });
                  }}
                >
                  Clear answer
                </button>
              ) : null}
            </fieldset>
          </li>
        ))}
      </ol>
      {error ? <p className="mt-3 text-sm text-red-700" role="alert">{error}</p> : null}
      {!submitted && q.open ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" className={`${btn} border border-navy text-navy`} disabled={busy} onClick={() => save(false)}>
            Save and finish later
          </button>
          {confirm ? (
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-navy p-2 text-sm" role="alertdialog" aria-label="Confirm submit">
              <span>
                Submit now? {data.items.length - answered ? `${data.items.length - answered} not answered. ` : ""}You cannot change answers after submitting.
              </span>
              <button type="button" className={`${btn} bg-navy text-cream`} disabled={busy} onClick={() => save(true)}>
                Yes, submit
              </button>
              <button type="button" className={`${btn} border border-rule`} onClick={() => setConfirm(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <button type="button" className={`${btn} bg-navy text-cream`} disabled={busy} onClick={() => setConfirm(true)}>
              Submit
            </button>
          )}
        </div>
      ) : null}
    </PageShell>
  );
}
