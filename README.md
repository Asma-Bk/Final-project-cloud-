# LOG8415E-Project
In this assignement, the goal is to set up a MySQL cluster on Amazon EC2 and experiment with
different cloud design patterns, mainly the Proxy and the Gatekeeper patterns. The first part is focused
on the implementation and configuration of a MySQL stand-alone on which the sakila database will
be installed. A benchmarking is also conducted to test the installations using the sysbench tool. The
second part aims to implement the cloud design patterns by adding the different components (Proxy,
Trusted Host and Gatekeeper) as different security and rerouting layers of MySQL cluster.