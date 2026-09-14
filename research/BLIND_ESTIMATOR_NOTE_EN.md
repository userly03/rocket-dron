# The Blind Estimator: Why a Monte Carlo with 100% Green Tests Can Still Measure the Wrong Question

**A case of pseudoreplication and statistic choice in swarm-weapon effectiveness simulation**

Author: `simulador-ew` project (independent research repository)
Date: 2026-09-13
Status: independent technical note, not peer-reviewed. Does not depend on the validity of any externally cited source — it is self-contained.

> This is a direct translation of `research/NOTA_ESTIMADOR_CIEGO.md` (Spanish original). Kept for reference; not submitted or announced anywhere.

---

## Abstract

While auditing a Monte Carlo simulator of high-power-microwave (HPM) weapon
effectiveness against drone swarms, we found that the primary estimator reported
`p̂ = 0` with a 95% confidence interval of width 0.32 — **even when the weapon had
actually caused casualties** (1 in 240 exposures). The code contained no
arithmetic error: all 123 tests in the suite passed, the Wilson interval
computation was correct, and the seed was reproducible. The defect was in **which
statistic was chosen to measure** and in **what was treated as the independent
sampling unit** — two experimental-design errors, not implementation errors, that
no unit test can catch on its own, because the code does exactly what it was
asked to do. We document the diagnosis, the fix (replacing a rare binary indicator
with a continuous per-replica statistic, with a percentile-bootstrap interval),
and the measured effect: in a scenario with real casualties, the interval
narrowed from width 0.32 to width 0.03 (~10×) and the point estimate stopped
being forced to zero. We generalize the finding into a checklist for any Monte
Carlo simulation of weapon, sensor, or intervention effectiveness against a
multi-unit system (swarms, formations, salvos), where the same pair of errors is
structurally easy to make.

---

## 1. The Problem, Abstractly

Any Monte Carlo simulation of "does this weapon work against this swarm?" must
answer two design questions before a single line of physics code is written:

1. **What per-run (replica) statistic is the quantity of interest?**
2. **What unit is treated as independent when computing uncertainty?**

Getting the first wrong produces an estimator that exists, runs, and **carries no
signal** in the operating region that matters. Getting the second wrong produces a
confidence interval that exists, is computed with a textbook formula, and **is
wrong — usually too narrow, or simply inapplicable — because it assumes
independence where none exists.** Neither error breaks a unit test: the code is
internally consistent with the question it was asked, only the question itself
was the wrong one. It is a silent failure mode.

### 1.1 Wrong statistic: rare all-or-nothing event instead of a graded response

If the physically interesting quantity is "how many swarm units ended up
neutralized," defining a replica's success as *"was 100% of the swarm
neutralized?"* collapses a graded response (0 to N casualties) into a binary
indicator that, outside a degenerate saturation regime, is 0 across nearly the
entire operationally relevant parameter space. The estimator then reports
`p̂ ≈ 0` with wide intervals not because the weapon has no effect, but because
**it was asked about the wrong event.**

### 1.2 Wrong independence unit: pseudoreplication

A second, related but distinct error appears if one tries to fix 1.1 by
aggregating individual outcomes across swarm units (e.g. "casualties per drone")
and computing a standard binomial interval (Wilson, Clopper-Pearson) treating
each drone as an independent Bernoulli trial. **They are not**: within a single
replica, every unit shares geometry, random seed, and weapon configuration. This
is a direct instance of what the ecological literature calls
**pseudoreplication**: treating correlated sub-samples as if they were
independent repetitions of the experiment (Hurlbert, 1984). The genuinely
independent sampling unit is **the entire replica**, not each unit within it.

---

## 2. Case Study: What We Found in Our Own Instrument

### 2.1 The system

An effectiveness simulator for an HPM weapon (continuous-wave cannon or missile)
against a drone swarm, with propagation physics (the Friis equation), cable
coupling, and a per-subsystem damage model calibrated against published
literature. The details of the damage model **are not relevant to this note** —
the defect described here is purely one of Monte Carlo experimental design, and
is independent of whether the underlying physics is well calibrated.

### 2.2 The original estimator and its measured failure

```
run_replica() → success = (neutralized == total_drones)   # all-or-nothing
```

Reference configuration: 25 kW cannon, 45° azimuth, circular swarm of 30 drones
at ~700 m, 8 replicas (240 drone-replica exposures total).

```
neutralized per replica:  0 0 0 0 0 1 0 0
p̂ (all-or-nothing)  = 0.0
95% CI (Wilson)      = [0.0, 0.3244]
```

**There was one real casualty in 240 exposures, and the estimator reported
exactly zero.** The Wilson computation over 8 Bernoulli replicas (was 100%
annihilated? yes/no) is itself statistically valid — each replica genuinely is
independent for that particular question. The defect is not in the arithmetic:
it is that "was the ENTIRE swarm annihilated?" is the wrong question for a weapon
that degrades the attacking force gradually. The information about that single
casualty existed in `neutralizados_por_replica` and was discarded before it ever
reached the final report.

### 2.3 The fix

Both the primary metric and the resampling unit were redefined:

- **Sampling unit:** the replica (not the individual drone).
- **Primary statistic:** `fraccion_media` — the mean, across replicas, of the
  fraction of drones neutralized within each replica. A continuous variable in
  [0,1], not a binary indicator.
- **Uncertainty:** a 95% confidence interval by **percentile bootstrap** (10,000
  resamples, fixed seed for exact reproducibility), resampling per-replica
  fractions — never individual drones. A Student-t interval is also reported as a
  cheap cross-check: if the two differ substantially, the underlying distribution
  is asymmetric, and that is information, not noise.
- **The all-or-nothing indicator is kept**, but demoted to an explicit secondary
  metric (`aniquilacion_total`), with its Wilson interval correctly computed at
  the replica level — precisely where that formula does apply.

### 2.4 The measured effect

With the corrected estimator, the same reference configuration (cannon at ~700 m)
today gives `fraccion_media = 0.0`, `95% CI = [0.0, 0.0]` — a *correct* zero: a
later, independent fix to the damage model (removing a sigmoid floor artifact,
out of scope for this note) eliminated spurious casualties that were previously
produced even at zero electric field. This zero differs in nature from the
`p̂ = 0.0` of §2.2: there, the zero concealed discarded information; here, the
zero is the physically correct answer, and the estimator says so with an interval
that collapses to a point instead of spanning `[0, 0.32]`.

To exhibit a case where there is a real effect, the same instrument was run with
a weapon that does engage the swarm (missile, detonation at ~80 m), 10 replicas,
30 drones per replica:

```
neutralized per replica:  1 0 0 0 2 0 0 0 0 1        (4 casualties in 300 exposures)

New metric — fraccion_media       = 0.0133   95% CI (bootstrap) = [0.0000, 0.0267]
Old metric — total annihilation   = 0.0      95% CI (Wilson)    = [0.0000, 0.2775]
```

**In the same scenario, with the same 4 real casualties, the old metric still
reports `p̂ = 0` with an interval of width 0.28** — because no replica had the
swarm 100% annihilated. The new metric does distinguish this scenario (with a
real, if small, effect) from the earlier one (no effect at all): `0.0133 > 0`,
with an interval ten times narrower than the one the old metric reported. Both
numbers, old and new, are computed over the same 10 replicas — the difference is
entirely the choice of what to measure, not a difference in data.

### 2.5 Validating the new estimator against known ground truth

That the interval narrowed does not by itself prove it is correctly computed —
a miscalculated interval can also be narrow — so it was checked against two
cases with known theoretical probability:

1. **Synthetic:** 60 replicas of `Bernoulli(p=0.35)` simulated directly (bypassing
   the physics engine). The bootstrap CI covers 0.35 with width < 0.15.
2. **Through the real physics engine:** a scenario constructed so every drone has
   *exactly* the same theoretical probability `p` — all at 20 m, on the beam axis
   (0° angular offset), with cabling tuned to the weapon's frequency (length
   coupling = 1) and polarization = 1 (total coupling = 1, no confounders). `p` is
   computed in closed form with the same Friis coupling formula the engine uses.
   Over 40 replicas, the bootstrap CI covers that theoretical `p`.

Neither case depends on the damage model being well calibrated against external
literature — both are ground truth by mathematical construction, not by the
authority of a cited source.

---

## 3. Why No Pre-Existing Unit Test Caught It

The suite's 123 tests passed before, during, and after the defect was found,
because they all verified that the code did **what it was told to do** (correct
Wilson arithmetic, reproducible seeds, correct aggregation of the all-or-nothing
indicator). None of them asked whether **what it was told to compute** was the
right quantity. This generalizes: a regression test protects against accidental
changes to a calculation that has already been decided; it does not protect
against having decided to compute the wrong thing in the first place. That
decision can only be audited by comparing the estimator against **known-ground-
truth cases external to the code itself** (§2.5), not by running the existing
suite more times.

---

## 4. A Generalizable Checklist

For anyone designing a Monte Carlo simulation of weapon, sensor, or intervention
effectiveness against a multi-unit system (swarms, formations, networks, salvos):

1. **Is the statistic of interest graded or all-or-nothing?** If the all-or-
   nothing event will be 0 (or 1) across most of the relevant operating space,
   measure the graded response instead (fraction, count, dose), and keep the
   extreme indicator as an explicit secondary metric.
2. **What is the genuinely independent unit?** If sub-observations within a run
   share a seed, geometry, or configuration, the run — not the sub-observation —
   is the resampling unit. Applying a binomial interval formula to correlated
   sub-observations is pseudoreplication, no matter how simple or "standard" the
   formula looks.
3. **Validate the estimator against a mathematically constructed known-ground-
   truth case**, not merely against the code not raising exceptions. A degenerate
   scenario (all units sharing the exact same theoretical probability) is cheap
   to build and depends on no external source.
4. **100% green tests is evidence of internal consistency, not of measuring the
   right question.** These are distinct claims, and the first does not imply the
   second.

---

## 5. Scope and Limitations

This note deals exclusively with **estimator and sampling-unit design**. It makes
no claim about whether the underlying physical damage model (coupling
thresholds, calibration against published literature) is correct — that is a
separate, unresolved question, and neither rests on this note nor does this note
rest on it. The concrete numbers cited (`fraccion_media = 0.0133`, etc.) are
output from this particular project's current damage model and **should not be
cited as a real effectiveness probability for any HPM system** — they serve only
to illustrate the magnitude of the change in the estimator, not as an operational
result.

No external author was contacted, and the argument of this note does not depend
on the validity of any third-party publication: the defect and its fix are
verified with self-contained mathematics (§2.5) and are fully reproducible from
this repository alone.

---

## 6. Reproducibility

- Repository: `simulador-ew` (independent research project).
- Commit introducing the fix (P1-A): `a408a39`.
- Implementation: `src/engine/experiments.py` (`run_replica` function,
  `ExperimentManager._summarize` class method, `intervalo_bootstrap` /
  `wilson_interval` functions).
- Tests encoding the cases in this document as permanent regression checks:
  `tests/test_experiments.py::TestIntervaloBootstrap::test_cubre_la_verdad_conocida`
  (synthetic case, §2.5),
  `tests/test_experiments.py::TestEstimadorTieneSenalEnElMotorReal::test_a_quemarropa_contra_verdad_conocida_del_motor`
  (real-engine case, §2.5),
  `tests/test_experiments.py::TestEstimadorTieneSenalEnElMotorReal::test_reporta_el_efecto_y_un_ic_mucho_mas_estrecho_que_v1`
  (direct numeric comparison against estimator v1, §2.4), and
  `tests/test_experiments.py::TestEstimadorTieneSenalEnElMotorReal::test_el_canion_a_700m_no_hace_nada_y_el_estimador_lo_dice`
  (the correct zero, §2.4).
- All numbers in this document can be reproduced by running those tests
  directly; none requires access to external data or dependencies.

---

## References

- Hurlbert, S.H. (1984). *Pseudoreplication and the design of ecological field
  experiments.* Ecological Monographs, 54(2), 187–211.
- Efron, B. & Tibshirani, R.J. (1993). *An Introduction to the Bootstrap.*
  Chapman & Hall/CRC.
- Wilson, E.B. (1927). *Probable inference, the law of succession, and statistical
  inference.* Journal of the American Statistical Association, 22(158), 209–212.
