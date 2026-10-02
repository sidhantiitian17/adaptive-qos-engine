Adaptive QoS Engine for Mixed Home Broadband Traffic
Background
A residential connection must concurrently support video conferencing, interactive gaming, voice, adaptive video, downloads, 
software updates and cloud backup. Static priority rules cannot always determine which activity matters at a particular moment. 
High throughput alone is insufficient if large queues introduce delay and jitter.
An adaptive QoS controller can observe link conditions and broad traffic behavior, apply fair scheduling, and change policy as 
demand changes. It should protect interactive applications while ensuring that bulk traffic continues to make 
reasonable progress.
For the student community, the intent is not to reproduce a proprietary commercial product. The objective is to create a 
technically credible reference implementation using openly documented interfaces and measurable experiments. The team 
should clearly describe the boundary between the prototype and a production-scale solution, including security, performance, 
hardware and operational considerations.
Challenge
Create an intent-aware QoS controller that classifies broad traffic categories without reading private payloads, estimates link 
capacity, applies queueing and shaping policies, and verifies whether the policy improved user experience. The controller should 
support a temporary user intent such as prioritizing a work call while retaining fairness.
The solution should be decomposed into independently testable modules. Teams should define inputs, outputs, state 
transitions, failure handling and success conditions for each module. Where AI is used, the project should compare it with a 
deterministic baseline and show that the model improves a measurable outcome rather than merely adding a conversational 
interface.
Illustrative Use Cases and Test Scenarios
◦ A large ISO download starts during a video conference; the controller limits the bulk queue and protects call latency.
◦ WAN bandwidth drops from 100 Mbps to 20 Mbps; the controller recalculates shaping rather than continuing to build a large 
queue.
◦ Three televisions stream video while a gaming device requires low latency; the system balances service quality across the 
household.
These examples are illustrative rather than exhaustive. Teams may add scenarios if they remain generic, ethically collected, openly 
reproducible and aligned with the central problem.

Constraints and Design Boundaries
◦ Do not decrypt application traffic.
◦ Use Linux traffic control or another open and inspectable enforcement mechanism.
◦ Support IPv4 and, where available, IPv6.
◦ Provide policy rollback and prevent starvation of low-priority traffic.
◦ Classifiers must expose confidence and allow correction of misclassification.
◦ The project must document third-party licenses and must not redistribute code, data or media contrary to its license.
◦ Generated data and network impairment settings must be included so that evaluators can reproduce important results.
◦ If a hardware capability is emulated, the report must label it as emulation and explain the model and its limitations.
◦ Credentials, private keys and tokens must not be committed to source control. Example secrets must be clearly fictitious.
◦ Automated remediation must be bounded, observable and reversible; failure must return the system to a known safe state.
Expected Output and Acceptance Evidence
◦ Traffic-class and link-capacity estimator.
◦ Dynamic QoS policy engine and enforcement module.
◦ Dashboard for latency, jitter, loss, throughput, queue depth and fairness.
◦ Automated baseline-versus-optimized experiments.
◦ API or user interface for temporary service intent.
◦ Architecture diagram showing device, edge, network, data, analytics and user-interface components.
◦ Setup guide containing prerequisites, exact versions, commands, configuration and verification steps.
◦ Automated or scripted demonstration that can reset the environment, introduce the selected condition, collect evidence and 
generate a result report.
◦ Known-limitations section explaining where real product hardware, certification, scale testing or proprietary integration 
would be required.
Evaluation Criteria
◦ Accuracy of classification and link estimation.
◦ Reduction in interactive latency, jitter and packet loss.
◦ Fairness and absence of starvation.
◦ Adaptation speed and policy stability.
◦ CPU overhead, reproducibility and clarity of results