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

