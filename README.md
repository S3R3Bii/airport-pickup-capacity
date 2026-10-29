# Airport-zone pickup capacity

Under a fixed retrospective simulation, the frozen 75th-percentile policy has **4.5% lower primary modeled cost** than the median, but **15.1% higher cost on the two named holiday dates**. Its raw-count error is higher. Capacity and cost assumptions change the policy comparison.

The practical value is testing assumptions before obtaining dispatch telemetry and fleet evidence. This is conditional on idealized prior-day count availability and hypothetical one-service-per-vehicle-hour capacity. Public historical records do not establish real-time availability, latent demand, physical queues, rider wait times or savings.

Start with the [decision summary and complete primary table](DECISION_SUMMARY.md), then the [protocol](PROTOCOL.md), [frozen selection](FREEZE.json), [source record](data/source/manifest.json), [complete results](results) and [independent manuscript](paper/manuscript.pdf).

![Conditional tradeoff](figures/capacity_tradeoff.png)

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python src/check_reproduction.py
python src/verify_figures.py
python src/verify_paper.py
python src/verify_public_package.py
```

Twelve fixtures; 21 protected dependencies; independent reconstruction of every validation/held prediction and scenario metric; 1,177,457 replay fields/documents; three original figures. Independent program research, not peer reviewed. No operational-readiness or novelty claim. Formal-publication projects including Azure remain private.
