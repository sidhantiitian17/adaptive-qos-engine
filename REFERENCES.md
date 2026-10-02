# References

Academic citations for the research papers and tools that informed the design of this prototype.

---

## Traffic Classification

```bibtex
@inproceedings{wickramasinghe2025netmatrix,
  title     = {Less is More: Simplifying Network Traffic Classification Leveraging RFCs},
  author    = {Wickramasinghe, Nimesha and Shaghaghi, Arash and Ferrari, Elena and Jha, Sanjay},
  booktitle = {Proceedings of The ACM Web Conference (WWW'25)},
  year      = {2025},
  note      = {NetMatrix: 3-feature (total\_length, TTL, inter-arrival time) + XGBoost classifier
               achieving 0.942 accuracy at 0.0005s/sample. Directly inspired our feature design.}
}

@article{lotfollahi2020deep,
  title   = {Deep Packet: A Novel Approach For Encrypted Traffic Classification Using Deep Learning},
  author  = {Lotfollahi, Mohammad and others},
  journal = {Soft Computing},
  year    = {2020},
  note    = {Survey on encrypted traffic classification methods (arXiv:2006.12352).
             Motivates payload-independent classification.}
}
```

## Link Capacity Estimation

```bibtex
@article{jain2003end,
  title   = {End-to-end available bandwidth: Measurement methodology, dynamics, and
             relation with TCP throughput},
  author  = {Jain, Manish and Dovrolis, Constantinos},
  journal = {IEEE/ACM Transactions on Networking},
  volume  = {11},
  number  = {4},
  pages   = {537--549},
  year    = {2003},
  note    = {SLoPS/Pathload methodology. Inspired our link\_estimator.py active probing design.}
}

@inproceedings{jain2004fallacies,
  title     = {Ten fallacies and pitfalls on end-to-end available bandwidth estimation},
  author    = {Jain, Manish and Dovrolis, Constantinos},
  booktitle = {Proceedings of the 4th ACM SIGCOMM conference on Internet measurement (IMC)},
  pages     = {272--277},
  year      = {2004},
  note      = {Design correctness checklist for bandwidth estimation. Informed our
               known\_limitations.md caveats about estimation accuracy.}
}

@inproceedings{hu2003evaluation,
  title     = {Evaluation and Characterization of Available Bandwidth Probing Techniques},
  author    = {Hu, Ningning and Steenkiste, Peter},
  booktitle = {IEEE JSAC},
  volume    = {21},
  number    = {6},
  year      = {2003},
  note      = {IGI/PTR bandwidth estimation techniques.}
}
```

## Enforcement & Queueing

```bibtex
@article{hoeiland2018cake,
  title   = {Piece of CAKE: A Comprehensive Queue Management Solution for Home Gateways},
  author  = {H\"{o}iland-J\o{}rgensen, Toke and Taht, Dave and Morton, Jonathan},
  journal = {IEEE International Symposium on Local and Metropolitan Area Networks (LANMAN)},
  year    = {2018},
  note    = {CAKE qdisc: DiffServ4 tin separation, host fairness, bandwidth shaping.
             Core enforcement mechanism used in this project.}
}
```

## Rollback & Safe-State Design

```bibtex
@article{koo1987checkpointing,
  title   = {Checkpointing and rollback-recovery for distributed systems},
  author  = {Koo, Richard and Toueg, Sam},
  journal = {IEEE Transactions on Software Engineering},
  volume  = {SE-13},
  number  = {1},
  pages   = {23--31},
  year    = {1987},
  note    = {Tentative vs permanent checkpoint distinction. Inspired our
             RollbackManager's apply-then-verify-then-commit pattern.}
}

@inproceedings{canini2013afro,
  title     = {A Framework for Fast and Controlled Software OpenFlow Updates},
  author    = {Canini, Marco and others},
  booktitle = {Proceedings of HotSDN'13},
  year      = {2013},
  note      = {AFRO: failure-triggered automatic recovery concept. Conceptual
               inspiration for bounded/observable/reversible remediation.}
}
```

## Reproducible Testbed & Network Emulation

```bibtex
@inproceedings{handigol2012reproducible,
  title     = {Reproducible network experiments using container-based emulation},
  author    = {Handigol, Nikhil and Heller, Brandon and Jeyakumar, Vimalkumar
               and Lantz, Bob and McKeown, Nick},
  booktitle = {Proceedings of the 8th international conference on Emerging networking
               experiments and technologies (CoNEXT)},
  pages     = {253--264},
  year      = {2012},
  note      = {Mininet-HiFi: validated CBE approach for reproducible networking research.
               Our raw netns/veth testbed follows the same principles.}
}

@misc{hemminger2005netem,
  title        = {Network Emulation with NetEm},
  author       = {Hemminger, Stephen},
  howpublished = {Linux Conf Au},
  year         = {2005},
  note         = {NetEm: kernel-level network emulator for controlled delay, loss, and
                  rate limiting. Used to emulate our WAN link conditions.}
}
```

## Intent Parsing

```bibtex
@misc{laya2024,
  title        = {Laya: Non-autoregressive typed-decision engine},
  author       = {Convai Innovations},
  howpublished = {\url{https://github.com/NandhaKishorM/laya}},
  year         = {2024},
  license      = {Apache 2.0},
  note         = {Used for natural-language intent parsing (choice/score/yes-no decisions).
                  Converts user requests like "prioritize my video call" into structured
                  QoS actions consumed by the deterministic policy engine.}
}
```
