# Measure-X

Measure-X is a tool for collecting performance metrics in a 5G network. 
Probes are coordinated to collect the following metrics: 
 - latency
 - throughput
 - age of information
 - energy

While some probes collect the metrics of interest, other probes can, at the same time, generate background traffic. 
The goal is to understand the impact of coexisting applications in terms of network metrics.

In its current implementation, probes are Raspberry PI single-board computers equipped with a 5G module. 

A Measure-X installation comprises the following elements: 
 - a coordinator: it's the Measure-X component that coordinates the probes and receives measurement specifications from the user
 - a number of probes: every probe is a measuring endpoint; probes are Raspberry PI5 devices equipped with a 5G module
 - an MQTT broker: it is used to make the coordinator and the probes communicate with each other. 
 
[INSTALLATION](./docs/INSTALLATION.md)

[EXAMPLES](./docs/EXAMPLES.md)

