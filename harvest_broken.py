Spezial-Collector NUR für den Code-Vault.

Quellen (priorisiert):
  - WikipediaCSCollector - DE+EN Wikipedia, gefiltert auf CS-Seeds
  - RFCCollector - IETF RFC plain-text (Netzwerktechnik)

Schreibt in CODE_VAULT_FILE + CODE_CACHE_FILE (inline-embedded mit
paraphrase-multilingual-MiniLM-L12-v2 - gleiches Modell wie der
Allgemein-Vault, daher 384-dim und kompatibel mit ChaosRetrieval).

Aufruf:
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase basics
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase languages
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase network
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase advanced
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase rfc
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase all

Resumable: bereits gesammelte IDs werden übersprungen.
Wirft NICHTS in den allgemeinen Vault. Nur CODE_VAULT_FILE.
"""
=======
Spezial-Collector NUR für den Code-Vault.

Quellen (priorisiert):
  - WikipediaCSCollector - DE+EN Wikipedia, gefiltert auf CS-Seeds
  - RFCCollector - IETF RFC plain-text (Netzwerktechnik)
  - ToolsCollector - Offizielle Dokumentationen für Compiler, Interpreter, Build-Tools

Schreibt in CODE_VAULT_FILE + CODE_CACHE_FILE (inline-embedded mit
paraphrase-multilingual-MiniLM-L12-v2 - gleiches Modell wie der
Allgemein-Vault, daher 384-dim und kompatibel mit ChaosRetrieval).

Aufruf:
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase basics
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase languages
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase network
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase advanced
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase tools
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase rfc
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase all

Resumable: bereits gesammelte IDs werden übersprungen.
Wirft NICHTS in den allgemeinen Vault. Nur CODE_VAULT_FILE.
"""
=======
Spezial-Collector NUR fuer den Code-Vault.
=======
# -*- coding: utf-8 -*-
"""
harvester/code_collectors.py
============================
Spezial-Collector NUR fuer den Code-Vault.
============================
Spezial-Collector NUR fuer den Code-Vault.

Quellen (priorisiert):
  - WikipediaCSCollector - DE+EN Wikipedia, gefiltert auf CS-Seeds
  - RFCCollector - IETF RFC plain-text (Netzwerktechnik)
  - ToolsCollector - Offizielle Dokumentationen fuer Compiler, Interpreter, Build-Tools

Schreibt in CODE_VAULT_FILE + CODE_CACHE_FILE (inline-embedded mit
paraphrase-multilingual-MiniLM-L12-v2 - gleiches Modell wie der
Allgemein-Vault, daher 384-dim und kompatibel mit ChaosRetrieval).

Aufruf:
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase basics
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase languages
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase network
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase advanced
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase tools
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase rfc
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase all

Resumable: bereits gesammelte IDs werden uebersprungen.
Wirft NICHTS in den allgemeinen Vault. Nur CODE_VAULT_FILE.
"""
============================
Spezial-Collector NUR für den Code-Vault.

Quellen (priorisiert):
  - WikipediaCSCollector - DE+EN Wikipedia, gefiltert auf CS-Seeds
  - RFCCollector - IETF RFC plain-text (Netzwerktechnik)
  - ToolsCollector - Offizielle Dokumentationen für Compiler, Interpreter, Build-Tools

Schreibt in CODE_VAULT_FILE + CODE_CACHE_FILE (inline-embedded mit
paraphrase-multilingual-MiniLM-L12-v2 - gleiches Modell wie der
Allgemein-Vault, daher 384-dim und kompatibel mit ChaosRetrieval).

Aufruf:
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase basics
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase languages
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase network
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase advanced
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase tools
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase rfc
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase all

Resumable: bereits gesammelte IDs werden übersprungen.
Wirft NICHTS in den allgemeinen Vault. Nur CODE_VAULT_FILE.
"""
============================
Spezial-Collector NUR für den Code-Vault.

Quellen (priorisiert):
  - WikipediaCSCollector - DE+EN Wikipedia, gefiltert auf CS-Seeds
  - RFCCollector - IETF RFC plain-text (Netzwerktechnik)

Schreibt in CODE_VAULT_FILE + CODE_CACHE_FILE (inline-embedded mit
paraphrase-multilingual-MiniLM-L12-v2 - gleiches Modell wie der
Allgemein-Vault, daher 384-dim und kompatibel mit ChaosRetrieval).

Aufruf:
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase basics
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase languages
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase network
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase advanced
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase rfc
  python3.12 -m framework.quelibrium.harvester.code_collectors --phase all

Resumable: bereits gesammelte IDs werden übersprungen.
Wirft NICHTS in den allgemeinen Vault. Nur CODE_VAULT_FILE.
"""
import os
import sys
import json
import time
import pickle
import urllib.parse
import urllib.request
import argparse
import warnings

import numpy as np

# vibelike Root
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
warnings.filterwarnings("ignore")

from framework.quelibrium.core.vault import Vault
from framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE


# ═════════════════════════════════════════════════════════════════════
# Seed-Listen (4 priorisierte Phasen)
# ═════════════════════════════════════════════════════════════════════

# Phase 1 - Basics: Grundlagen Programmierung & Informatik
BASICS_SEEDS_DE = [
    "Programmierung", "Algorithmus", "Datenstruktur", "Variable (Programmierung)",
    "Schleife (Programmierung)", "Rekursion", "Funktion (Programmierung)",
    "Bedingte Anweisung", "Iteration", "Komplexitätstheorie",
    "Landau-Symbole", "Berechenbarkeit", "Turing-Maschine",
    "Boolesche Algebra", "Logikgatter", "Binärsystem", "Hexadezimalsystem",
    "Bit", "Byte", "ASCII", "Unicode", "UTF-8",
    "Compiler", "Interpreter", "Maschinencode", "Assemblersprache",
    "Hochsprache", "Quelltext",
    "Datentyp", "Zeichenkette", "Ganzzahl", "Fließkommazahl",
    "Liste (Datenstruktur)", "Stapelspeicher", "Warteschlange (Datenstruktur)",
    "Baum (Datenstruktur)", "Hashtabelle", "Verkettete Liste", "Array",
    "Sortierverfahren", "Suchalgorithmus", "Quicksort", "Mergesort",
    "Binäre Suche", "Tiefensuche", "Breitensuche",
    "Pseudocode", "Flussdiagramm", "Objektorientierte Programmierung",
    "Funktionale Programmierung", "Imperative Programmierung",
    "Deklarative Programmierung", "Logische Programmierung",
    "Klasse (Programmierung)", "Vererbung (Programmierung)", "Polymorphismus (Programmierung)",
    "Kapselung (Programmierung)", "Abstraktion (Programmierung)", "Schnittstelle (Programmierung)",
]
BASICS_SEEDS_EN = [
    "Computer programming", "Algorithm", "Data structure", "Variable (computer science)",
    "Control flow", "Recursion (computer science)", "Subroutine",
    "Conditional (computer programming)", "Iteration",
    "Computational complexity theory", "Big O notation", "Computability theory",
    "Turing machine", "Boolean algebra", "Logic gate",
    "Binary number", "Hexadecimal", "Bit", "Byte", "ASCII", "Unicode", "UTF-8",
    "Compiler", "Interpreter (computing)", "Machine code", "Assembly language",
    "High-level programming language", "Source code",
    "Data type", "String (computer science)", "Integer (computer science)",
    "Floating-point arithmetic", "List (abstract data type)",
    "Stack (abstract data type)", "Queue (abstract data type)",
    "Tree (data structure)", "Hash table", "Linked list", "Array data structure",
    "Sorting algorithm", "Search algorithm", "Quicksort", "Merge sort",
    "Binary search", "Depth-first search", "Breadth-first search",
    "Pseudocode", "Flowchart", "Object-oriented programming",
    "Functional programming", "Imperative programming",
    "Declarative programming", "Logic programming",
    "Class (computer programming)", "Inheritance (object-oriented programming)",
    "Polymorphism (computer science)", "Encapsulation (computer programming)",
    "Abstraction (computer science)", "Interface (computing)",
]

# Phase 2 - Programmiersprachen
LANGUAGES_SEEDS_DE = [
    "Python (Programmiersprache)", "JavaScript", "TypeScript",
    "Rust (Programmiersprache)", "Go (Programmiersprache)",
    "C (Programmiersprache)", "C++", "C-Sharp",
    "Java (Programmiersprache)", "Kotlin (Programmiersprache)",
    "Ruby (Programmiersprache)", "PHP", "Perl", "Bash (Shell)",
    "Lua", "Haskell (Programmiersprache)", "Erlang (Programmiersprache)",
    "Elixir (Programmiersprache)", "Scala (Programmiersprache)",
    "Clojure", "Racket (Programmiersprache)", "Scheme (Programmiersprache)",
    "Lisp (Programmiersprache)", "Common Lisp",
    "Fortran", "COBOL", "Pascal (Programmiersprache)",
    "SQL", "R (Programmiersprache)", "Julia (Programmiersprache)",
    "Dart (Programmiersprache)", "Swift (Programmiersprache)",
    "Objective-C", "Assemblersprache",
    "HTML", "CSS", "JSON", "XML", "YAML", "Regulärer Ausdruck",
    "Git", "GitHub",
]
LANGUAGES_SEEDS_EN = [
    "Python (programming language)", "JavaScript", "TypeScript",
    "Rust (programming language)", "Go (programming language)",
    "C (programming language)", "C++", "C Sharp (programming language)",
    "Java (programming language)", "Kotlin (programming language)",
    "Ruby (programming language)", "PHP", "Perl",
    "Bash (Unix shell)", "Lua (programming language)",
    "Haskell", "Erlang (programming language)", "Elixir (programming language)",
    "Scala (programming language)", "Clojure",
    "Racket (programming language)", "Scheme (programming language)",
    "Lisp (programming language)", "Common Lisp",
    "Fortran", "COBOL", "Pascal (programming language)",
    "SQL", "R (programming language)", "Julia (programming language)",
    "Dart (programming language)", "Swift (programming language)",
    "Objective-C", "Assembly language",
    "HTML", "Cascading Style Sheets", "JSON", "XML", "YAML",
    "Regular expression", "Git", "GitHub",
    # Frameworks/Libraries die häufig referenziert werden
    "React (JavaScript library)", "Vue.js", "Angular (web framework)",
    "Svelte", "Next.js", "Django (web framework)", "Flask (web framework)",
    "FastAPI", "Express.js", "Node.js", "Bun (software)", "Deno",
    "TensorFlow", "PyTorch", "NumPy", "pandas (software)", "scikit-learn",
]

# Phase 3 - Netzwerktechnik
NETWORK_SEEDS_DE = [
    "Computernetzwerk", "OSI-Modell", "TCP/IP-Referenzmodell",
    "Transmission Control Protocol", "User Datagram Protocol", "Internet Protocol",
    "IPv4", "IPv6", "Subnetz", "CIDR", "Routing", "Routing-Tabelle",
    "Border Gateway Protocol", "OSPF", "RIP (Protokoll)",
    "Ethernet", "MAC-Adresse", "ARP", "VLAN", "Switch (Netzwerktechnik)",
    "Router", "Firewall", "Gateway (Netzwerk)", "NAT",
    "Hypertext Transfer Protocol", "HTTPS", "Transport Layer Security",
    "DNS", "DHCP", "FTP", "SSH (Netzwerkprotokoll)", "Telnet",
    "Simple Mail Transfer Protocol", "POP3", "IMAP",
    "WebSocket", "QUIC", "HTTP/2", "HTTP/3",
    "Public-Key-Kryptosystem", "Symmetrisches Kryptosystem", "Hash-Funktion",
    "MD5", "SHA-2", "AES (Algorithmus)", "RSA-Kryptosystem",
    "Digitale Signatur", "Zertifikat (Informationssicherheit)",
    "Virtuelles privates Netzwerk", "Proxyserver", "Reverse Proxy",
    "Lastverteilung", "Content Delivery Network",
    "Denial of Service", "Man-in-the-Middle-Angriff",
]
NETWORK_SEEDS_EN = [
    "Computer network", "OSI model", "Internet protocol suite",
    "Transmission Control Protocol", "User Datagram Protocol", "Internet Protocol",
    "IPv4", "IPv6", "Subnetwork", "Classless Inter-Domain Routing",
    "Routing", "Routing table", "Border Gateway Protocol",
    "Open Shortest Path First", "Routing Information Protocol",
    "Ethernet", "MAC address", "Address Resolution Protocol", "VLAN",
    "Network switch", "Router (computing)", "Firewall (computing)",
    "Default gateway", "Network address translation",
    "Hypertext Transfer Protocol", "HTTPS", "Transport Layer Security",
    "Domain Name System", "Dynamic Host Configuration Protocol",
    "File Transfer Protocol", "Secure Shell", "Telnet",
    "Simple Mail Transfer Protocol", "Post Office Protocol",
    "Internet Message Access Protocol", "WebSocket", "QUIC",
    "HTTP/2", "HTTP/3",
    "Public-key cryptography", "Symmetric-key algorithm",
    "Cryptographic hash function", "MD5", "SHA-2", "Advanced Encryption Standard",
    "RSA (cryptosystem)", "Digital signature", "Public key certificate",
    "Virtual private network", "Proxy server", "Reverse proxy",
    "Load balancing (computing)", "Content delivery network",
    "Denial-of-service attack", "Man-in-the-middle attack",
]

# Phase 4 - Komplexere Themen (Compiler, OS, Distributed Systems, Crypto)
ADVANCED_SEEDS_DE = [
    "Betriebssystem", "Kernel (Betriebssystem)", "Linux (Kernel)", "Unix",
    "Prozess (Informatik)", "Thread (Informatik)", "Scheduler (Informatik)",
    "Speicherverwaltung", "Virtueller Speicher", "Paging",
    "Dateisystem", "Inode", "Berechtigungssystem",
    "Verteiltes System", "Konsensalgorithmus", "Paxos (Algorithmus)", "Raft (Informatik)",
    "CAP-Theorem", "Konsistenzmodell", "Eventually consistent",
    "MapReduce", "Apache Hadoop", "Apache Spark", "Apache Kafka",
    "Datenbank", "Relationale Datenbank", "NoSQL", "Transaktion (Informatik)",
    "ACID", "Indizierung (Datenbank)", "B-Baum",
    "Compilerbau", "Lexikalische Analyse", "Parser",
    "Abstrakter Syntaxbaum", "Codeoptimierung",
    "Typsystem", "Statische Typisierung", "Dynamische Typisierung",
    "Garbage Collection", "Speicherleck",
    "Künstliche Intelligenz", "Maschinelles Lernen", "Neuronales Netz",
    "Deep Learning", "Convolutional Neural Network", "Rekurrentes neuronales Netz",
    "Transformer (Maschinelles Lernen)", "Großes Sprachmodell",
    "Container (Virtualisierung)", "Docker (Software)", "Kubernetes",
    "Microservices", "Software-Architektur", "Domain-driven Design",
    "Entwurfsmuster", "Singleton (Entwurfsmuster)", "Factory (Entwurfsmuster)",
    "Observer (Entwurfsmuster)", "Model View Controller",
    "Versionsverwaltung", "Continuous Integration", "DevOps",
]
ADVANCED_SEEDS_EN = [
    "Operating system", "Kernel (operating system)", "Linux kernel", "Unix",
    "Process (computing)", "Thread (computing)", "Scheduling (computing)",
    "Memory management", "Virtual memory", "Paging",
    "File system", "Inode", "File-system permissions",
    "Distributed computing", "Consensus (computer science)", "Paxos (computer science)",
    "Raft (algorithm)", "CAP theorem", "Consistency model", "Eventual consistency",
    "MapReduce", "Apache Hadoop", "Apache Spark", "Apache Kafka",
    "Database", "Relational database", "NoSQL", "Database transaction",
    "ACID", "Database index", "B-tree",
    "Compiler", "Lexical analysis", "Parsing",
    "Abstract syntax tree", "Compiler optimization",
    "Type system", "Type safety", "Dynamic programming language",
    "Garbage collection (computer science)", "Memory leak",
    "Artificial intelligence", "Machine learning", "Artificial neural network",
    "Deep learning", "Convolutional neural network", "Recurrent neural network",
    "Transformer (deep learning architecture)", "Large language model",
    "OS-level virtualization", "Docker (software)", "Kubernetes",
    "Microservices", "Software architecture", "Domain-driven design",
    "Software design pattern", "Singleton pattern", "Factory method pattern",
    "Observer pattern", "Model-view-controller",
    "Version control", "Continuous integration", "DevOps",
]

# Phase 5 - DATABASES
DATABASES_SEEDS_DE = [
    "Datenbank", "Relationale Datenbank", "SQL", "Datenbankmanagementsystem",
    "Datenbankindex", "Datenbankschema", "Datenbanknormalisierung", "Transaktion (Informatik)",
    "ACID", "Foreign Key", "Primärschlüssel", "Join (SQL)",
    "PostgreSQL", "MySQL", "MariaDB", "SQLite", "Oracle Database", "Microsoft SQL Server",
    "NoSQL", "MongoDB", "Redis", "Apache Cassandra", "Elasticsearch", "Neo4j",
    "Graphdatenbank", "Schlüssel-Werte-Datenbank", "Dokumentenorientierte Datenbank", "Spaltenorientierte Datenbank",
    "Data Warehouse", "OLTP", "OLAP", "ETL-Prozess",
    "B-Baum", "Bloom-Filter", "Datenintegrität", "Concurrency Control",
    "Object-Relational Mapping", "CAP-Theorem", "Eventual Consistency", "Sharding",
]
DATABASES_SEEDS_EN = [
    "Database", "Relational database", "SQL", "Database management system",
    "Database index", "Database schema", "Database normalization", "Database transaction",
    "ACID", "Foreign key", "Primary key", "Join (SQL)", "Stored procedure", "View (SQL)",
    "PostgreSQL", "MySQL", "MariaDB", "SQLite", "Oracle Database", "Microsoft SQL Server",
    "NoSQL", "MongoDB", "Redis", "Apache Cassandra", "Elasticsearch", "Neo4j", "CouchDB",
    "Graph database", "Key-value database", "Document-oriented database", "Column-oriented DBMS",
    "Time series database", "In-memory database",
    "Data warehouse", "Online transaction processing", "Online analytical processing", "Extract, transform, load",
    "B-tree", "B+ tree", "Bloom filter", "Database engine", "Concurrency control", "Database tuning",
    "Object-relational mapping", "CAP theorem", "Eventual consistency", "Database sharding",
    "Replication (computing)", "Two-phase commit protocol", "Multiversion concurrency control",
]

# Phase 6 - SECURITY
SECURITY_SEEDS_DE = [
    "Kryptographie", "Symmetrisches Kryptosystem", "Asymmetrisches Kryptosystem",
    "Advanced Encryption Standard", "RSA-Kryptosystem", "Elliptic Curve Cryptography",
    "Digitale Signatur", "Hashfunktion", "SHA-2", "SHA-3", "MD5",
    "Public-Key-Infrastruktur", "Zertifizierungsstelle", "X.509", "Transport Layer Security",
    "OAuth", "OpenID Connect", "JSON Web Token", "Single Sign-on", "Zwei-Faktor-Authentisierung",
    "SQL-Injection", "Cross-Site-Scripting", "Cross-Site-Request-Forgery",
    "Man-in-the-Middle-Angriff", "Denial-of-Service-Attacke",
    "Firewall", "Intrusion Detection System", "Penetrationstest",
    "Zero Trust", "Sandbox (Computer)", "Sicherheitslücke",
    "Pufferüberlauf", "Datenschutz", "DSGVO",
]
SECURITY_SEEDS_EN = [
    "Cryptography", "Symmetric-key algorithm", "Public-key cryptography",
    "Advanced Encryption Standard", "RSA (cryptosystem)", "Elliptic-curve cryptography",
    "Diffie-Hellman key exchange", "Digital signature", "Cryptographic hash function",
    "SHA-2", "SHA-3", "HMAC", "Argon2", "bcrypt", "PBKDF2",
    "Public key infrastructure", "Certificate authority", "X.509", "Transport Layer Security",
    "OAuth", "OpenID Connect", "JSON Web Token", "SAML", "Single sign-on", "Multi-factor authentication",
    "OWASP", "SQL injection", "Cross-site scripting", "Cross-site request forgery",
    "Man-in-the-middle attack", "Denial-of-service attack", "Phishing", "Buffer overflow",
    "Privilege escalation", "Side-channel attack", "Heap overflow",
    "Firewall (computing)", "Intrusion detection system", "Penetration test", "Vulnerability (computing)",
    "Zero trust security model", "Sandbox (computer security)", "Information security",
    "General Data Protection Regulation", "Secure coding", "Threat model",
]

# Phase 7 - DEVOPS (Container, Orchestration, CI/CD, Cloud, Monitoring)
DEVOPS_SEEDS_DE = [
    "DevOps", "Continuous Integration", "Continuous Delivery", "Continuous Deployment",
    "Docker (Software)", "Container (Virtualisierung)", "Kubernetes", "Containerisierung",
    "Virtuelle Maschine", "Hypervisor", "Cloud Computing", "Infrastructure as a Service",
    "Platform as a Service", "Software as a Service", "Serverless Computing",
    "Amazon Web Services", "Microsoft Azure", "Google Cloud Platform",
    "Microservices", "Service Mesh", "Reverse Proxy", "Load Balancer",
    "Configuration Management", "Infrastructure as Code", "Ansible", "Terraform",
    "Git", "GitLab", "GitHub", "Jenkins (Software)",
    "Logfile", "Prometheus (Software)", "Grafana",
    "Site Reliability Engineering", "Blue-Green Deployment",
]
DEVOPS_SEEDS_EN = [
    "DevOps", "Continuous integration", "Continuous delivery", "Continuous deployment",
    "Docker (software)", "Container (computing)", "Kubernetes", "OS-level virtualization",
    "Virtual machine", "Hypervisor", "Cloud computing", "Infrastructure as a service",
    "Platform as a service", "Software as a service", "Function as a service", "Serverless computing",
    "Amazon Web Services", "Microsoft Azure", "Google Cloud Platform", "Cloudflare",
    "Microservices", "Service mesh", "Reverse proxy", "Load balancing (computing)",
    "API gateway", "Sidecar pattern",
    "Configuration management", "Infrastructure as code", "Ansible (software)", "Terraform (software)",
    "Puppet (software)", "Chef (software)", "Helm (package manager)",
    "Git", "GitLab", "GitHub", "Jenkins (software)", "Argo CD",
    "Logging (computing)", "Prometheus (software)", "Grafana", "OpenTelemetry",
    "Site reliability engineering", "Blue-green deployment", "Canary release", "Feature toggle",
]

# Phase 8 - ALGORITHMS (klassische CS-Algorithmen + Datenstrukturen)
ALGORITHMS_SEEDS_DE = [
    "Algorithmus", "Datenstruktur", "Komplexitätstheorie", "Landau-Symbole",
    "Sortierverfahren", "Quicksort", "Mergesort", "Heapsort", "Insertionsort", "Radixsort",
    "Suchalgorithmus", "Binäre Suche", "Lineare Suche", "Hashtabelle",
    "Verkettete Liste", "Stapelspeicher", "Warteschlange (Datenstruktur)",
    "Baum (Datenstruktur)", "Binärer Suchbaum", "AVL-Baum", "Rot-Schwarz-Baum",
    "Graph (Graphentheorie)", "Breitensuche", "Tiefensuche", "Dijkstra-Algorithmus", "A*-Algorithmus",
    "Dynamische Programmierung", "Greedy-Algorithmus", "Backtracking", "Divide and Conquer",
    "Rekursion", "Memoisation",
    "Reguläre Sprache", "Endlicher Automat",
    "P-NP-Problem", "Approximationsalgorithmus",
]
ALGORITHMS_SEEDS_EN = [
    "Algorithm", "Data structure", "Computational complexity", "Big O notation",
    "Sorting algorithm", "Quicksort", "Merge sort", "Heapsort", "Insertion sort", "Radix sort",
    "Bubble sort", "Selection sort", "Timsort",
    "Search algorithm", "Binary search algorithm", "Linear search", "Hash table",
    "Linked list", "Stack (abstract data type)", "Queue (abstract data type)", "Priority queue",
    "Tree (data structure)", "Binary search tree", "AVL tree", "Red-black tree", "Trie",
    "Graph (abstract data type)", "Breadth-first search", "Depth-first search",
    "Dijkstras algorithm", "A* search algorithm", "Bellman-Ford algorithm", "Floyd-Warshall algorithm",
    "Dynamic programming", "Greedy algorithm", "Backtracking", "Divide-and-conquer algorithm",
    "Recursion (computer science)", "Memoization", "Tail call",
    "Regular language", "Finite-state machine", "Turing machine",
    "P versus NP problem", "Approximation algorithm", "NP-hardness",
]

# Phase 9 - TOOLS (Compiler, Interpreter, Build-Tools, Test-Runner, VCS)
TOOLS_SEEDS_DE = [
    # Compiler
    "GNU Compiler Collection", "GCC", "Clang", "LLVM",
    "Tiny C Compiler", "Rust Compiler", "Go Compiler",
    "Microsoft Visual C++", "Intel C++ Compiler", "Portland Group",
    "Java Compiler (javac)", "C# Compiler (csc)", "Swift Compiler",
    "Fortran Compiler (gfortran)", "D language", "Zig (Programmiersprache)",
    "Nim (Programmiersprache)", "Crystal (Programmiersprache)",
    # Build Systems
    "Make (Software)", "CMake", "Meson (Software)", "Bazel",
    "Ninja (Build System)", "Autoconf", "Automake", "Libtool",
    "Maven", "Gradle", "Ant (Software)", "SBT", "Cargo (Rust)",
    "pip (Package Manager)", "conda", "npm", "Yarn (Package Manager)",
    "Docker (Software)", "Podman", "Buildah", "LXC",
    # Test Runner
    "pytest", "unittest (Python)", "JUnit", "TestNG", "xUnit",
    "Google Test", "Catch2", "Boost.Test", "CTest", "Doctest",
    "RSpec", "Minitest", "Jest (JavaScript)", "Mocha (JavaScript)",
    "Vitest", "Cypress", "Selenium", "Playwright (Software)",
    "Robot Framework", "Cucumber (Software)", "Behave (Software)",
    # Version Control
    "Git", "GitHub", "GitLab", "Bitbucket", "Mercurial",
    "Subversion (Software)", "Fossil (SCM)", "Darcs", "Pijul",
    # Debugging & Profiling
    "GDB", "LLDB", "Valgrind", "AddressSanitizer", "UndefinedBehaviorSanitizer",
    "perf (Linux)", "strace", "ltrace", "tcpdump", "Wireshark",
    "FlameGraph", "py-spy", "cProfile", "line_profiler",
    # Packaging
    "dpkg", "rpm", "apt (Software)", "yum", "dnf", "pacman (Package Manager)",
    "Homebrew", "Chocolatey", "Scoop (Installer)", "Flatpak", "Snap (Software)",
    # Shells & Scripting
    "Bash (Unix shell)", "Z shell", "Fish (shell)", "PowerShell",
    "AWK", "sed", "grep", "find (Unix)", "xargs", "jq (Programming language)",
    "Coreutils", "GNU findutils", "GNU grep", "GNU sed",
    # Containers & Virtualization
    "Docker (software)", "Docker Compose", "Kubernetes", "Helm (package manager)",
    "containerd", "runc", "OCI", "CRI-O", "CNI", "BuildKit",
    "LXC", "LXD (software)", "QEMU", "KVM", "VirtualBox", "VMware",
    # CI/CD
    "GitHub Actions", "GitLab CI/CD", "Jenkins (software)", "CircleCI",
    "Travis CI", "Drone CI", "Concourse", "Tekton (software)", "Argo Workflows",
    # Security
    "OpenSSL", "LibreSSL", "GnuTLS", "mbed TLS", "BoringSSL",
    "GPG", "OpenPGP", "SSH (Netzwerkprotokoll)", "TLS", "SSL",
    # Networking
    "curl", "wget", "netcat", "socat", "nmap", "masscan",
    "iptables", "nftables", "iproute2", "ss (Unix)", "ip (Unix)",
    # Databases
    "SQLite", "PostgreSQL", "MySQL", "MariaDB", "MongoDB",
    "Redis", "Memcached", "Elasticsearch", "Cassandra", "Neo4j",
    # Monitoring & Logging
    "Prometheus (software)", "Grafana", "Loki (software)", "Tempo",
    "ELK Stack", "Fluentd", "Logstash", "Kibana",
    "syslog", "rsyslog", "journald",
    # Text Processing
    "Pandoc", "Asciidoctor", "Sphinx (documentation generator)",
    "Doxygen", "Jekyll (software)", "Hugo (static site generator)",
    "mkdocs", "reStructuredText", "Markdown",
    # Misc Tools
    "jq (Programming language)", "fzf", "ripgrep", "fd (command)",
    "bat (command)", "exa (command)", "delta (pager)", "glow (markdown)",
    "htop", "iostat", "vmstat", "dstat", "sar (Unix)",
    "tmux", "screen (Software)", "neovim", "Vim (text editor)", "Emacs",
]

TOOLS_SEEDS_EN = [
    # Compiler
    "GNU Compiler Collection", "GCC", "Clang", "LLVM",
    "Tiny C Compiler", "Rust (programming language)", "Go (programming language)",
    "Microsoft Visual C++", "Intel C++ Compiler", "Portland Group",
    "javac", "C Sharp (programming language)", "Swift (programming language)",
    "Fortran", "D (programming language)", "Zig (programming language)",
    "Nim (programming language)", "Crystal (programming language)",
    # Build Systems
    "Make (software)", "CMake", "Meson (software)", "Bazel",
    "Ninja (build system)", "Autoconf", "Automake", "Libtool",
    "Apache Maven", "Gradle", "Apache Ant", "sbt", "Cargo (Rust)",
    "pip (package manager)", "conda", "npm", "Yarn (package manager)",
    "Docker (software)", "Podman", "Buildah", "LXC",
    # Test Runner
    "pytest", "unittest (Python)", "JUnit", "TestNG", "xUnit",
    "Google Test", "Catch2", "Boost.Test", "CTest", "Doctest",
    "RSpec", "Minitest", "Jest (JavaScript framework)", "Mocha (JavaScript framework)",
    "Vitest", "Cypress (testing framework)", "Selenium (software)", "Playwright (framework)",
    "Robot Framework", "Cucumber (software)", "Behave (software)",
    # Version Control
    "Git", "GitHub", "GitLab", "Bitbucket", "Mercurial",
    "Apache Subversion", "Fossil (SCM)", "Darcs", "Pijul",
    # Debugging & Profiling
    "GNU Debugger", "LLDB", "Valgrind", "AddressSanitizer", "UndefinedBehaviorSanitizer",
    "perf (Linux)", "strace", "ltrace", "tcpdump", "Wireshark",
    "FlameGraph", "py-spy", "cProfile", "line_profiler",
    # Packaging
    "dpkg", "rpm", "APT (software)", "yum", "DNF (software)", "pacman (package manager)",
    "Homebrew", "Chocolatey", "Scoop (installer)", "Flatpak", "Snap (software)",
    # Shells & Scripting
    "Bash (Unix shell)", "Z shell", "Fish (shell)", "PowerShell",
    "AWK", "sed", "grep", "find (Unix)", "xargs", "jq",
    "Coreutils", "GNU findutils", "GNU grep", "GNU sed",
    # Containers & Virtualization
    "Docker (software)", "Docker Compose", "Kubernetes", "Helm (package manager)",
    "containerd", "runc", "OCI", "CRI-O", "CNI", "BuildKit",
    "LXC", "LXD (software)", "QEMU", "KVM", "VirtualBox", "VMware",
    # CI/CD
    "GitHub Actions", "GitLab CI/CD", "Jenkins (software)", "CircleCI",
    "Travis CI", "Drone CI", "Concourse", "Tekton (software)", "Argo Workflows",
    # Security
    "OpenSSL", "LibreSSL", "GnuTLS", "mbed TLS", "BoringSSL",
    "GPG", "OpenPGP", "Secure Shell", "Transport Layer Security",
    # Networking
    "curl", "wget", "netcat", "socat", "nmap", "masscan",
    "iptables", "nftables", "iproute2", "ss (Unix)", "ip (Unix)",
    # Databases
    "SQLite", "PostgreSQL", "MySQL", "MariaDB", "MongoDB",
    "Redis", "Memcached", "Elasticsearch", "Apache Cassandra", "Neo4j",
    # Monitoring & Logging
    "Prometheus (software)", "Grafana", "Loki (software)", "Tempo",
    "ELK Stack", "Fluentd", "Logstash", "Kibana",
    "syslog", "rsyslog", "journald",
    # Text Processing
    "Pandoc", "Asciidoctor", "Sphinx (documentation generator)",
    "Doxygen", "Jekyll (software)", "Hugo (static site generator)",
    "MkDocs", "reStructuredText", "Markdown",
    # Misc Tools
    "jq (Programming language)", "fzf", "ripgrep", "fd (command)",
    "bat (command)", "exa (command)", "delta (pager)", "glow (markdown)",
    "htop", "iostat", "vmstat", "dstat", "sar (Unix)",
    "tmux", "GNU Screen", "Neovim", "Vim (text editor)", "Emacs",
]

# Phase 9 - RFCs (IETF Netzwerk-Standards). RFC-Nummern: Auswahl der bekanntesten.
RFC_NUMBERS = [
    # Core Internet
    791, 792, 793, 1034, 1035, 1122, 1123, 2131, 2616, 7230, 7540, 9114,
    # Mail
    5321, 5322, 1939, 3501,
    # Crypto/TLS
    8446, 5246, 5280, 6749, 7519, 7515,
    # SSH/SFTP
    4251, 4252, 4253, 4254,
    # IPv6
    2460, 8200, 4861, 4862,
    # BGP/OSPF
    4271, 2328, 5340,
    # NAT, ICMP, ARP
    826, 3022, 4787, 5389,
    # DNS Sec
    4033, 4034, 4035,
    # WebSocket, QUIC, HTTP/3
    6455, 9000, 9114,
    # Markdown, CommonMark base
    7763, 7764,
    # JSON, JSON Schema
    8259, 7159,
    # OAuth
    6749, 6750,
    # Modern HTTP semantics (replaces 7230-7235)
    9110, 9111, 9112, 9113,
    # OAuth 2.1 family - Token, PKCE, JWT Bearer, Token Exchange
    7521, 7522, 7523, 7636, 8693,
    # SMTP-ext, IMAP, MIME
    6376, 7208, 6376, 2045, 2046, 2047,
    # gRPC / HTTP/2 settings, ALPN
    7301, 7838,
    # WebRTC, SDP, ICE/STUN/TURN basics
    8825, 4566, 5245, 5766,
    # Important security RFCs
    7515, 7516, 7517, 7518, 7519,
]


# ═════════════════════════════════════════════════════════════════════
# CodeVaultWriter - schreibt Docs + Embeddings in Code-Vault
# ═════════════════════════════════════════════════════════════════════

class CodeVaultWriter:
    """Atomic-append-Wrapper um Vault + Embedding-Cache.

    Lädt beide Files beim Start, sammelt neue Docs intern, schreibt
    in Batches auf Disk. Inline-Embedding mit multilingual MiniLM
    (gleiches Modell wie Allgemein-Vault → 384-dim, kompatibel mit
    ChaosRetrieval).
    """

    EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, device: str = "cuda"):
        print(f"[code-vault] Loading model: {self.EMBEDDING_MODEL} (device={device})")
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(self.EMBEDDING_MODEL, device=device)

        self.vault = Vault(CODE_VAULT_FILE)
        try:
            self.archive = self.vault.load() or []
        except Exception:
            self.archive = []
        print(f"[code-vault] Existing docs: {len(self.archive)}")

        # Embedding-Cache
        if os.path.exists(CODE_CACHE_FILE):
            try:
                with open(CODE_CACHE_FILE, "rb") as f:
                    self.cache = pickle.load(f)
            except Exception:
                self.cache = {}
        else:
            self.cache = {}
        print(f"[code-vault] Existing embeddings: {len(self.cache)}")

        self.existing_ids = set(str(d.get("id", "")) for d in self.archive)
        self._buffer = []

    def has(self, doc_id: str) -> bool:
        return str(doc_id) in self.existing_ids

    def add(self, doc: dict):
        """Buffer einen neuen Doc. flush() schreibt auf Disk."""
        doc_id = str(doc.get("id", ""))
        if not doc_id or doc_id in self.existing_ids:
            return False
        self._buffer.append(doc)
        self.existing_ids.add(doc_id)
        return True

    def flush(self, batch_size: int = 64):
        if not self._buffer:
            return 0
        # Embed in Batches
        texts = []
        for d in self._buffer:
            t = d.get("content") or d.get("text") or ""
            if not isinstance(t, str):
                t = str(t)
            texts.append(t[:512] if t else "(empty)")

        embs = self.model.encode(
            texts, batch_size=batch_size,
            convert_to_numpy=True, show_progress_bar=False
        )
        for d, e in zip(self._buffer, embs):
            self.cache[str(d.get("id"))] = e.astype("float32")
            self.archive.append(d)

        n = len(self._buffer)
        self._buffer.clear()

        # Auf Disk
        self.vault.save(self.archive)
        tmp = CODE_CACHE_FILE + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(self.cache, f, protocol=4)
        os.replace(tmp, CODE_CACHE_FILE)
        return n


# ═════════════════════════════════════════════════════════════════════
# WikipediaCSCollector
# ═════════════════════════════════════════════════════════════════════

WIKI_API_DE = "https://de.wikipedia.org/w/api.php"
WIKI_API_EN = "https://en.wikipedia.org/w/api.php"
# Wikipedia-Policy: UA MUSS Kontakt (email/url) enthalten - sonst hartes Ratelimit.
# Siehe https://meta.wikimedia.org/wiki/User-Agent_policy
USER_AGENT = (
    "QuelibriumCodeHarvester/1.0 "
    "(https://github.com/jnrabit/collect; jakobnotter89@googlemail.com)"
)

# Rate-Limit Parameter
WIKI_SLEEP_BASE = 0.6          # Mindestpause zwischen Requests (s)
WIKI_SLEEP_JITTER = 0.4        # Zufalls-Aufschlag (0..N s)
WIKI_RETRY_MAX = 4             # Max Retries bei 429
WIKI_RETRY_BACKOFF = (5, 15, 45, 90)  # Backoff-Sequenz (s) bei 429
WIKI_INTER_SECTOR_COOLDOWN = 10  # Pause zwischen Sektor-Wechseln (s)


def _wiki_fetch(api_url: str, title: str) -> dict:
    """Holt extract + Metadaten für einen Wikipedia-Titel.
    Eingebauter 429-Retry mit Backoff (Retry-After-Header wird respektiert)."""
    import random
    params = {
        "action": "query", "format": "json",
        "titles": title, "prop": "extracts|info",
        "exintro": "0", "explaintext": "1",
        "inprop": "url",
        "maxlag": "5",  # Server drosselt selbst statt 429 - höflicher
    }
    url = api_url + "?" + urllib.parse.urlencode(params)

    last_err = None
    for attempt in range(WIKI_RETRY_MAX):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return None
            page = next(iter(pages.values()))
            if "missing" in page or "extract" not in page:
                return None
            return page

        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < WIKI_RETRY_MAX - 1:
                # Retry-After-Header bevorzugen, sonst Backoff-Tabelle
                retry_after = e.headers.get("Retry-After", "")
                try:
                    wait_s = int(retry_after) if retry_after.isdigit() else WIKI_RETRY_BACKOFF[attempt]
                except Exception:
                    wait_s = WIKI_RETRY_BACKOFF[attempt]
                wait_s += random.uniform(0, 2)
                print(f"    429 für {title} - backoff {wait_s:.1f}s (attempt {attempt+1}/{WIKI_RETRY_MAX})")
                time.sleep(wait_s)
                continue
            # Andere HTTP-Errors oder letzter Versuch → raise
            raise

    if last_err:
        raise last_err
    return None


def harvest_wikipedia_seeds(writer: CodeVaultWriter, seeds: list, lang: str,
                            sector: str, source_tag: str):
    """Pro Seed: Wiki-Extract holen, Doc bauen, in Buffer adden."""
    import random
    api = WIKI_API_DE if lang == "de" else WIKI_API_EN
    added = 0
    skipped = 0
    failed = 0
    consecutive_429 = 0

    print(f"\n[wiki:{lang}] {len(seeds)} seeds, sector={sector}")
    for i, title in enumerate(seeds, 1):
        # Resumable: doc_id = wiki:<lang>:<title>
        doc_id = f"WIKI_CS-{lang}-{title.replace( , _)}"
        if writer.has(doc_id):
            skipped += 1
            continue

        try:
            page = _wiki_fetch(api, title)
            consecutive_429 = 0  # Reset bei Erfolg
            if not page or not page.get("extract"):
                failed += 1
                continue
            extract = page["extract"]
            if len(extract) < 200:  # Stubs überspringen
                failed += 1
                continue

            writer.add({
                "id": doc_id,
                "content": extract,
                "title": page.get("title", title),
                "source": source_tag,
                "sector": sector,
                "url": page.get("fullurl", ""),
                "lang": lang,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1

            # Progress + Flush alle 16
            if added % 16 == 0:
                n = writer.flush()
                print(f"  [{i}/{len(seeds)}] +{added} added, {skipped} skip, {failed} fail - saved {n}")

            # Rate-Limiting: Basis + Jitter (sanftes Spacing)
            time.sleep(WIKI_SLEEP_BASE + random.uniform(0, WIKI_SLEEP_JITTER))

        except urllib.error.HTTPError as e:
            failed += 1
            if e.code == 429:
                consecutive_429 += 1
                # Notbremse: nach 5 hintereinander 429 → 2min Pause
                if consecutive_429 >= 5:
                    print(f"    🚨 5x 429 in Folge - Notbremse 120s")
                    time.sleep(120)
                    consecutive_429 = 0
            if failed <= 5:
                print(f"    skip {title}: HTTP {e.code}")
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"    skip {title}: {type(e).__name__}: {str(e)[:80]}")

    # Final flush
    n = writer.flush()
    print(f"[wiki:{lang}] done: +{added} added, {skipped} skipped, {failed} failed")
    return added


# ═════════════════════════════════════════════════════════════════════
# RFCCollector
# ═════════════════════════════════════════════════════════════════════

RFC_URL = "https://www.rfc-editor.org/rfc/rfc{n}.txt"


def harvest_rfcs(writer: CodeVaultWriter, rfc_numbers: list):
    added = 0
    skipped = 0
    failed = 0
    print(f"\n[rfc] {len(rfc_numbers)} RFCs")

    for i, num in enumerate(rfc_numbers, 1):
        doc_id = f"RFC-{num}"
        if writer.has(doc_id):
            skipped += 1
            continue

        try:
            url = RFC_URL.format(n=num)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8", errors="replace")

            if len(text) < 500:
                failed += 1
                continue

            # Title-Heuristik: erste Zeile mit Wörtern
            title_line = ""
            for line in text.split("\n")[:30]:
                stripped = line.strip()
                if len(stripped) > 10 and "Request for Comments" not in stripped:
                    title_line = stripped
                    break
            title = f"RFC {num}" + (f": {title_line[:80]}" if title_line else "")

            writer.add({
                "id": doc_id,
                "content": text[:5000],  # Erste 5k Zeichen ist genug für Embedding
                "title": title,
                "source": "IETF_RFC",
                "sector": "NETWORK_PROTOCOL",
                "url": url,
                "lang": "en",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1

            if added % 8 == 0:
                n = writer.flush()
                print(f"  [{i}/{len(rfc_numbers)}] +{added}, saved {n}")

            time.sleep(0.3)
        except Exception as e:
            failed += 1
            print(f"    RFC {num} skip: {type(e).__name__}")

    n = writer.flush()
    print(f"[rfc] done: +{added}, {skipped} skipped, {failed} failed")
    return added


# ═════════════════════════════════════════════════════════════════════
# Python PEP Collector
# ═════════════════════════════════════════════════════════════════════
# PEPs (Python Enhancement Proposals) decken alle relevanten Sprach-,
# Style- und Library-Konventionen ab. URL-Pattern: peps.python.org/pep-NNNN.rst
# (RST-Plain-Text - gut zu embedden).

PEP_NUMBERS = [
    # Style + Coding Conventions
    8, 7, 20, 257, 3107, 484, 526, 563, 604, 612, 646, 692, 695,
    # Language Features
    255, 343, 380, 492, 525, 530, 572, 634, 654, 657, 695, 701,
    # Packaging + Distribution
    517, 518, 621, 660, 668, 720,
    # Async / IO
    3156, 3153, 525, 530,
    # Typing-related
    483, 484, 526, 544, 561, 585, 591, 593, 612, 646, 673,
    # Versioning + Release
    440, 602, 664,
    # Numeric / Performance
    3118, 657,
]

def harvest_peps(writer: CodeVaultWriter, pep_numbers: list):
    """Holt PEP-RST-Text von peps.python.org und embeddet ihn als Code-Doc."""
    import random
    base_url = "https://peps.python.org/pep-{:04d}/"
    rst_url  = "https://peps.python.org/api/peps.json"  # für Titel/Meta (1 Call)
    added = 0
    skipped = 0
    failed = 0

    # Optional: PEP-Metadata (für Titel)
    pep_titles = {}
    try:
        req = urllib.request.Request(rst_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        for k, v in meta.items():
            try:
                pep_titles[int(k)] = v.get("title", "")
            except (ValueError, AttributeError):
                continue
        print(f"[pep] Metadata geladen ({len(pep_titles)} PEP-Titel)")
    except Exception as e:
        print(f"[pep] Metadata-Fehler (egal): {e}")

    # Dedupe - manche PEPs sind in PEP_NUMBERS doppelt aufgeführt
    seen = set()
    unique_numbers = [n for n in pep_numbers if n not in seen and not seen.add(n)]

    print(f"\n[pep] {len(unique_numbers)} PEPs")
    for i, num in enumerate(unique_numbers, 1):
        doc_id = f"PEP-{num:04d}"
        if writer.has(doc_id):
            skipped += 1
            continue

        url = base_url.format(num)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            # Sehr einfache HTML-Cleanup: Body-Inhalt grob extrahieren
            import re as _re
            # Entferne Scripts/Styles
            html = _re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
            html = _re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
            # HTML-Tags entfernen
            text = _re.sub(r"<[^>]+>", " ", html)
            # HTML-Entities (basics)
            text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "))
            # Whitespace normalisieren
            text = _re.sub(r"\s+", " ", text).strip()

            if len(text) < 300:
                failed += 1
                continue

            # Auf erste ~4000 chars limitieren (sonst zu viel pro embedding)
            text = text[:4000]

            writer.add({
                "id": doc_id,
                "content": text,
                "title": f"PEP {num}: {pep_titles.get(num, )}".strip(": "),
                "source": "PYTHON_PEP",
                "sector": "PEP",
                "url": url,
                "lang": "en",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1

            if added % 8 == 0:
                n = writer.flush()
                print(f"  [{i}/{len(unique_numbers)}] +{added}, saved {n}")

            time.sleep(0.4 + random.uniform(0, 0.3))

        except urllib.error.HTTPError as e:
            failed += 1
            if failed <= 5:
                print(f"    PEP {num} skip: HTTP {e.code}")
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"    PEP {num} skip: {type(e).__name__}")

    n = writer.flush()
    print(f"[pep] done: +{added}, {skipped} skipped, {failed} failed")
    return added


# ═════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════

PHASE_MAP = {
    "basics":     (BASICS_SEEDS_DE, BASICS_SEEDS_EN, "BASICS", "WIKI_CS_BASICS"),
    "languages":  (LANGUAGES_SEEDS_DE, LANGUAGES_SEEDS_EN, "LANGUAGES", "WIKI_CS_LANGUAGES"),
    "network":    (NETWORK_SEEDS_DE, NETWORK_SEEDS_EN, "NETWORK", "WIKI_CS_NETWORK"),
    "advanced":   (ADVANCED_SEEDS_DE, ADVANCED_SEEDS_EN, "ADVANCED", "WIKI_CS_ADVANCED"),
    "databases":  (DATABASES_SEEDS_DE, DATABASES_SEEDS_EN, "DATABASES", "WIKI_CS_DATABASES"),
    "security":   (SECURITY_SEEDS_DE, SECURITY_SEEDS_EN, "SECURITY", "WIKI_CS_SECURITY"),
    "devops":     (DEVOPS_SEEDS_DE, DEVOPS_SEEDS_EN, "DEVOPS", "WIKI_CS_DEVOPS"),
    "algorithms": (ALGORITHMS_SEEDS_DE, ALGORITHMS_SEEDS_EN, "ALGORITHMS", "WIKI_CS_ALGORITHMS"),
    "tools":      (TOOLS_SEEDS_DE, TOOLS_SEEDS_EN, "TOOLS", "WIKI_CS_TOOLS"),
}

ALL_PHASES = ["basics", "languages", "network", "advanced",
              "databases", "security", "devops", "algorithms", "tools", "rfc", "pep",
              "mdn", "manpages", "lang_docs"]


# ═════════════════════════════════════════════════════════════════════
# MDNCollector - Mozilla Developer Network Documentation
# ═════════════════════════════════════════════════════════════════════

MDN_API = "https://developer.mozilla.org/api/v1"
MDN_BASE = "https://developer.mozilla.org"

# Wichtige MDN-Sektionen für IT-Coder
MDN_SECTIONS = [
    # Web APIs
    "Web/API",
    "Web/HTTP",
    "Web/JavaScript",
    "Web/HTML",
    "Web/CSS",
    "Web/SVG",
    "Web/WebGL",
    "Web/WebSockets",
    "Web/Web_Components",
    # JavaScript
    "JavaScript/Reference",
    "JavaScript/Guide",
    # HTML
    "HTML/Reference",
    "HTML/Guide",
    # CSS
    "CSS/Reference",
    "CSS/Guide",
    # Security
    "Web/Security",
    "Web/Privacy",
    # Performance
    "Web/Performance",
]


def _mdn_fetch(url: str) -> dict:
    """Holt MDN-Inhalte über API oder Fallback zu HTML."""
    import random
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"    MDN API Fehler: {e}")
        return None


def _mdn_extract_html(url: str) -> str:
    """Extrahiert Text aus MDN-HTML-Seite."""
    import re as _re
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        
        # Entferne Scripts, Styles, Navbar, Footer
        html = _re.sub(r"<script[^>]*>.*?</script>", "", html, flags=_re.DOTALL | _re.IGNORECASE)
        html = _re.sub(r"<style[^>]*>.*?</style>", "", html, flags=_re.DOTALL | _re.IGNORECASE)
        
        # Hauptinhalt extrahieren (MDN nutzt <main> oder <article>)
        main_match = _re.search(r"<main[^>]*>(.*?)</main>", html, flags=_re.DOTALL | _re.IGNORECASE)
        if main_match:
            html = main_match.group(1)
        else:
            article_match = _re.search(r"<article[^>]*>(.*?)</article>", html, flags=_re.DOTALL | _re.IGNORECASE)
            if article_match:
                html = article_match.group(1)
        
        # HTML-Tags entfernen
        text = _re.sub(r"<[^>]+>", " ", html)
        # HTML-Entities
        text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                    .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "))
        # Whitespace normalisieren
        text = _re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"    MDN HTML Fehler: {e}")
        return None


def harvest_mdn(writer: CodeVaultWriter):
    """Sammelt MDN Web Docs."""
    added = 0
    skipped = 0
    failed = 0
    
    print(f"\n[mdn] {len(MDN_SECTIONS)} Sektionen")
    
    for section in MDN_SECTIONS:
        # API-URL für Inhaltsverzeichnis
        api_url = f"{MDN_API}/doc/{section}"
        
        try:
            data = _mdn_fetch(api_url)
            if not data or "documents" not in data:
                # Fallback: versuche direkte Seite
                html_url = f"{MDN_BASE}/en-US/docs/{section}"
                text = _mdn_extract_html(html_url)
                if text and len(text) > 500:
                    doc_id = f"MDN-{section.replace(/, _)}"
                    if writer.has(doc_id):
                        skipped += 1
                        continue
                    writer.add({
                        "id": doc_id,
                        "content": text[:5000],
                        "title": f"MDN: {section}",
                        "source": "MDN_WEB_DOCS",
                        "sector": "WEB_TECHNOLOGIES",
                        "url": f"{MDN_BASE}/en-US/docs/{section}",
                        "lang": "en",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    added += 1
                else:
                    failed += 1
                continue
            
            # Verarbeite API-Ergebnis
            for doc_data in data.get("documents", []):
                title = doc_data.get("title", "")
                url = doc_data.get("url", "")
                if not title or not url:
                    continue
                
                # HTML holen und extrahieren
                text = _mdn_extract_html(f"{MDN_BASE}{url}")
                if not text or len(text) < 300:
                    failed += 1
                    continue
                
                doc_id = f"MDN-{url.replace(/, _).replace(., _)}"
                if writer.has(doc_id):
                    skipped += 1
                    continue
                
                writer.add({
                    "id": doc_id,
                    "content": text[:5000],
                    "title": f"MDN: {title}",
                    "source": "MDN_WEB_DOCS",
                    "sector": "WEB_TECHNOLOGIES",
                    "url": f"{MDN_BASE}{url}",
                    "lang": "en",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                added += 1
                
                if added % 16 == 0:
                    n = writer.flush()
                    print(f"  [{section}] +{added}, saved {n}")
                
                time.sleep(0.5 + random.uniform(0, 0.5))
                
        except Exception as e:
            failed += 1
            print(f"    Section {section} Fehler: {e}")
    
    n = writer.flush()
    print(f"[mdn] done: +{added}, {skipped} skipped, {failed} failed")
    return added


# ═════════════════════════════════════════════════════════════════════
# ManPageCollector - Linux man-pages
# ═════════════════════════════════════════════════════════════════════

# Wichtige man-Sektionen: 2=Syscalls, 3=Libraries
# Nur existierende Pages (man7.org)
MAN_SECTIONS = [
    ("2", ["open", "read", "write", "close", "stat", "fstat", "lseek", "mmap", 
          "ioctl", "fcntl", "flock", "dup", "dup2", "pipe", "fork", "execve",
          "exit", "wait", "waitpid", "kill", "signal", "sigaction", "pause",
          "alarm", "setitimer", "gettimeofday", "nanosleep", "sched_yield",
          "clone", "vfork", "uname", "getpid", "getppid", "getuid", "getgid",
          "setuid", "setgid", "getrlimit", "setrlimit", "brk", "sbrk",
          "mprotect", "mlock", "munlock", "madvise", "mincore", "getpagesize",
          "getdents", "gettid", "tgkill", "futex", "epoll_create", "epoll_ctl",
          "epoll_wait", "inotify_init", "prctl", "rt_sigaction", "rt_sigsuspend"]),
    
    ("3", ["malloc", "free", "realloc", "calloc", "memalign", "posix_memalign",
          "printf", "fprintf", "sprintf", "snprintf", "scanf", "fscanf",
          "fopen", "fclose", "fread", "fwrite", "fseek", "ftell", "rewind",
          "fgetc", "fputc", "getc", "putc", "ungetc", "fgets", "fputs",
          "getline", "perror", "strerror", "strtol", "strtoul", "strtod",
          "atoi", "atol", "atof", "strdup", "strndup", "memcpy", "memmove",
          "memset", "memcmp", "strlen", "strnlen", "strcmp", "strncmp",
          "strcasecmp", "strncasecmp", "strchr", "strrchr", "strstr", "strtok",
          "qsort", "bsearch", "dlsym", "dlopen", "dlclose", "dlerror",
          "pthread_create", "pthread_join", "pthread_mutex_lock", "pthread_cond_wait"]),
]

# man-pages online (falls lokal nicht verfügbar)
MAN_ONLINE = "https://man7.org/linux/man-pages/man{section}/{name}.{section}.html"


def _man_fetch(section: str, name: str) -> str:
    """Holt man-page von man7.org."""
    try:
        url = MAN_ONLINE.format(section=section, name=name)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        
        import re as _re
        # man7.org: mehrere <pre> Blöcke - alle extrahieren und concatenieren
        pre_blocks = _re.findall(r"<pre>(.*?)</pre>", html, flags=_re.DOTALL)
        if pre_blocks:
            text = "\n".join(pre_blocks)
        else:
            # Fallback: versuche <div class="content"> oder ähnlich
            content_match = _re.search(r<pre[^>]*>(.*?)</pre>, html, flags=_re.DOTALL)
            text = content_match.group(1) if content_match else html
        
        # HTML-Tags entfernen
        text = _re.sub(r"<[^>]+>", "", text)
        # HTML-Entities
        text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                    .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "))
        # Whitespace normalisieren (aber Zeilenumbrüche erhalten für man-pages)
        text = _re.sub(r"[ \t]+", " ", text).strip()
        return text
    except Exception as e:
        print(f"    man {section} {name} Fehler: {e}")
        return None


def harvest_manpages(writer: CodeVaultWriter):
    """Sammelt Linux man-pages (Syscalls + Libraries)."""
    added = 0
    skipped = 0
    failed = 0
    
    print(f"\n[manpages] {sum(len(names) for _, names in MAN_SECTIONS)} pages")
    
    for section, names in MAN_SECTIONS:
        for name in names:
            doc_id = f"MAN-{section}-{name}"
            if writer.has(doc_id):
                skipped += 1
                continue
            
            text = _man_fetch(section, name)
            if not text or len(text) < 100:
                failed += 1
                continue
            
            writer.add({
                "id": doc_id,
                "content": text[:8000],
                "title": f"man {section} {name}",
                "source": "LINUX_MAN_PAGES",
                "sector": "SYSTEMS_PROGRAMMING",
                "url": MAN_ONLINE.format(section=section, name=name),
                "lang": "en",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1
            
            if added % 16 == 0:
                n = writer.flush()
                print(f"  [section {section}] +{added}, saved {n}")
            
            time.sleep(0.3 + random.uniform(0, 0.3))
    
    n = writer.flush()
    print(f"[manpages] done: +{added}, {skipped} skipped, {failed} failed")
    return added


# ═════════════════════════════════════════════════════════════════════
# ToolsCollector - Dokumentationen für Compiler, Interpreter, Build-Tools
# ═════════════════════════════════════════════════════════════════════

# Tool-Dokumentations-URLs (offizielle Docs)
TOOL_DOCS = [
    # Compiler
    {
        "id": "GCC_DOCS",
        "urls": [
            "https://gcc.gnu.org/onlinedocs/gcc-13.2.0/gcc/",
            "https://gcc.gnu.org/onlinedocs/gcc-13.2.0/gccint/",
            "https://gcc.gnu.org/onlinedocs/libstdc++/latest/",
        ],
        "sector": "COMPILERS",
        "source": "GCC_OFFICIAL",
    },
    {
        "id": "CLANG_DOCS",
        "urls": [
            "https://clang.llvm.org/docs/",
            "https://clang.llvm.org/docs/CommandGuide/clang.html",
            "https://clang.llvm.org/docs/LanguageExtensions.html",
        ],
        "sector": "COMPILERS",
        "source": "CLANG_OFFICIAL",
    },
    {
        "id": "RUST_DOCS",
        "urls": [
            "https://doc.rust-lang.org/std/index.html",
            "https://doc.rust-lang.org/book/",
            "https://doc.rust-lang.org/rust-by-example/",
            "https://doc.rust-lang.org/nomicon/",
        ],
        "sector": "COMPILERS",
        "source": "RUST_OFFICIAL",
    },
    {
        "id": "GO_DOCS",
        "urls": [
            "https://pkg.go.dev/std",
            "https://go.dev/doc/",
            "https://go.dev/doc/effective_go",
        ],
        "sector": "COMPILERS",
        "source": "GO_OFFICIAL",
    },
    # Build Systems
    {
        "id": "CMAKE_DOCS",
        "urls": [
            "https://cmake.org/cmake/help/latest/",
            "https://cmake.org/cmake/help/latest/guide/tutorial/index.html",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "CMAKE_OFFICIAL",
    },
    {
        "id": "MESON_DOCS",
        "urls": [
            "https://mesonbuild.com/Quick-guide.html",
            "https://mesonbuild.com/Reference-manual.html",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "MESON_OFFICIAL",
    },
    {
        "id": "BAZEL_DOCS",
        "urls": [
            "https://bazel.build/start",
            "https://bazel.build/rules/lib/rules/",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "BAZEL_OFFICIAL",
    },
    # Test Runner
    {
        "id": "PYTEST_DOCS",
        "urls": [
            "https://docs.pytest.org/en/stable/",
            "https://docs.pytest.org/en/stable/how-to/usage.html",
            "https://docs.pytest.org/en/stable/how-to/fixtures.html",
        ],
        "sector": "TEST_RUNNERS",
        "source": "PYTEST_OFFICIAL",
    },
    {
        "id": "JUNIT_DOCS",
        "urls": [
            "https://junit.org/junit5/docs/current/user-guide/",
            "https://junit.org/junit5/docs/current/api/",
        ],
        "sector": "TEST_RUNNERS",
        "source": "JUNIT_OFFICIAL",
    },
    {
        "id": "GOOGLE_TEST_DOCS",
        "urls": [
            "https://google.github.io/googletest/",
            "https://google.github.io/googletest/primer.html",
        ],
        "sector": "TEST_RUNNERS",
        "source": "GOOGLE_TEST_OFFICIAL",
    },
    # Git
    {
        "id": "GIT_DOCS",
        "urls": [
            "https://git-scm.com/doc",
            "https://git-scm.com/docs/user-manual.html",
            "https://git-scm.com/docs/git-glossary.html",
        ],
        "sector": "VERSION_CONTROL",
        "source": "GIT_OFFICIAL",
    },
    # Debugging
    {
        "id": "GDB_DOCS",
        "urls": [
            "https://sourceware.org/gdb/current/onlinedocs/gdb/",
            "https://sourceware.org/gdb/wiki/ Internals/",
        ],
        "sector": "DEBUGGING",
        "source": "GDB_OFFICIAL",
    },
    {
        "id": "VALGRIND_DOCS",
        "urls": [
            "https://valgrind.org/docs/manual/manual.html",
        ],
        "sector": "DEBUGGING",
        "source": "VALGRIND_OFFICIAL",
    },
    # Networking
    {
        "id": "CURL_DOCS",
        "urls": [
            "https://curl.se/docs/",
            "https://curl.se/docs/manpage.html",
        ],
        "sector": "NETWORKING",
        "source": "CURL_OFFICIAL",
    },
    {
        "id": "OPENSSL_DOCS",
        "urls": [
            "https://www.openssl.org/docs/",
            "https://www.openssl.org/docs/manmaster/man1/",
        ],
        "sector": "SECURITY",
        "source": "OPENSSL_OFFICIAL",
    },
    # Containers
    {
        "id": "DOCKER_DOCS",
        "urls": [
            "https://docs.docker.com/",
            "https://docs.docker.com/reference/",
            "https://docs.docker.com/engine/reference/commandline/cli/",
        ],
        "sector": "CONTAINERS",
        "source": "DOCKER_OFFICIAL",
    },
    {
        "id": "KUBERNETES_DOCS",
        "urls": [
            "https://kubernetes.io/docs/home/",
            "https://kubernetes.io/docs/reference/",
        ],
        "sector": "CONTAINERS",
        "source": "KUBERNETES_OFFICIAL",
    },
    # Shells
    {
        "id": "BASH_DOCS",
        "urls": [
            "https://www.gnu.org/software/bash/manual/",
            "https://www.gnu.org/software/bash/manual/bash.html",
        ],
        "sector": "SHELLS",
        "source": "BASH_OFFICIAL",
    },
]


def harvest_tool_docs(writer: CodeVaultWriter):
    """Sammelt offizielle Dokumentationen für Tools."""
    added = 0
    skipped = 0
    failed = 0

    print(f"\n[tools] {len(TOOL_DOCS)} Tool-Dokumentationen")

    for doc_config in TOOL_DOCS:
        base_id = doc_config["id"]
        urls = doc_config["urls"]
        sector = doc_config["sector"]
        source = doc_config["source"]

        for i, url in enumerate(urls):
            doc_id = f"{base_id}-{i}"
            if writer.has(doc_id):
                skipped += 1
                continue

            text = _fetch_url(url)
            if not text or len(text) < 500:
                failed += 1
                continue

            # Titel aus URL extrahieren
            title = url.split("/")[-1].replace(".html", "").replace("-", " ")
            if not title or title == "index":
                title = f"{source}: Documentation {i+1}"

            writer.add({
                "id": doc_id,
                "content": text[:8000],
                "title": f"{source}: {title}".strip(": "),
                "source": source,
                "sector": sector,
                "url": url,
                "lang": "en",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1

            if added % 8 == 0:
                n = writer.flush()
                print(f"  +{added}, saved {n}")

            time.sleep(1.0 + random.uniform(0, 0.5))

    n = writer.flush()
    print(f"[tools] done: +{added}, {skipped} skipped, {failed} failed")
    return added


# ═════════════════════════════════════════════════════════════════════
# LanguageDocsCollector - Offizielle Sprach-Dokumentationen
# ═════════════════════════════════════════════════════════════════════

# Wichtige Sprach-Dokus
LANG_DOCS = [
    # CPython
    {
        "id": "CPYTHON_DOCS",
        "urls": [
            "https://docs.python.org/3/library/functions.html",
            "https://docs.python.org/3/reference/datamodel.html",
            "https://docs.python.org/3/c-api/index.html",
            "https://docs.python.org/3/extending/index.html",
        ],
        "sector": "PYTHON_INTERNALS",
        "source": "CPYTHON_DOCS",
    },
    # Rust
    {
        "id": "RUST_DOCS",
        "urls": [
            "https://doc.rust-lang.org/std/index.html",
            "https://doc.rust-lang.org/book/ch00-00-introduction.html",
            "https://doc.rust-lang.org/nomicon/index.html",
            "https://doc.rust-lang.org/reference/index.html",
        ],
        "sector": "RUST_LANGUAGE",
        "source": "RUST_DOCS",
    },
    # Go
    {
        "id": "GO_DOCS",
        "urls": [
            "https://pkg.go.dev/std",
            "https://go.dev/doc/effective_go",
            "https://go.dev/doc/concurrency",
        ],
        "sector": "GO_LANGUAGE", 
        "source": "GO_DOCS",
    },
]


def _fetch_url(url: str) -> str:
    """Holt Text von einer URL."""
    import re as _re
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        
        # Einfache Text-Extraktion
        text = _re.sub(r"<script[^>]*>.*?</script>", "", html, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<style[^>]*>.*?</style>", "", text, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                    .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "))
        text = _re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"    URL {url} Fehler: {e}")
        return None


def harvest_lang_docs(writer: CodeVaultWriter):
    """Sammelt offizielle Sprach-Dokumentationen."""
    added = 0
    skipped = 0
    failed = 0
    
    print(f"\n[lang_docs] {len(LANG_DOCS)} Sprach-Dokus")
    
    for doc_config in LANG_DOCS:
        base_id = doc_config["id"]
        urls = doc_config["urls"]
        sector = doc_config["sector"]
        source = doc_config["source"]
        
        for i, url in enumerate(urls):
            doc_id = f"{base_id}-{i}"
            if writer.has(doc_id):
                skipped += 1
                continue
            
            text = _fetch_url(url)
            if not text or len(text) < 500:
                failed += 1
                continue
            
            # Titel aus URL extrahieren
            title = url.split("/")[-1].replace(".html", "").replace("-", " ")
            
            writer.add({
                "id": doc_id,
                "content": text[:8000],
                "title": f"{source}: {title}",
                "source": source,
                "sector": sector,
                "url": url,
                "lang": "en",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1
            
            if added % 8 == 0:
                n = writer.flush()
                print(f"  +{added}, saved {n}")
            
            time.sleep(1.0 + random.uniform(0, 0.5))
    
    n = writer.flush()
    print(f"[lang_docs] done: +{added}, {skipped} skipped, {failed} failed")
    return added


def main():
    parser = argparse.ArgumentParser(description="Code-Vault Harvester")
    parser.add_argument(
        "--phase", required=True,
        choices=ALL_PHASES + ["all"],
        help="Harvest-Phase. all fährt alle hintereinander.",
    )
    parser.add_argument("--device", default="cuda",
                        help="cuda (GPU) oder cpu für embedding")
    args = parser.parse_args()

    writer = CodeVaultWriter(device=args.device)
    total_added = 0
    start = time.time()

    phases = ALL_PHASES if args.phase == "all" else [args.phase]

    for phase_idx, phase in enumerate(phases):
        if phase == "rfc":
            total_added += harvest_rfcs(writer, RFC_NUMBERS)
        elif phase == "pep":
            total_added += harvest_peps(writer, PEP_NUMBERS)
        elif phase == "mdn":
            total_added += harvest_mdn(writer)
        elif phase == "manpages":
            total_added += harvest_manpages(writer)
        elif phase == "lang_docs":
            total_added += harvest_lang_docs(writer)
        elif phase == "tools":
            total_added += harvest_tool_docs(writer)
        else:
            seeds_de, seeds_en, sector, source_tag = PHASE_MAP[phase]
            total_added += harvest_wikipedia_seeds(writer, seeds_de, "de", sector, source_tag)
            # Sanftes Spacing zwischen DE und EN - vermeidet 429 bei Sektor-Wechsel
            if seeds_en:
                print(f"  ... cooldown {WIKI_INTER_SECTOR_COOLDOWN}s vor [wiki:en] ...")
                time.sleep(WIKI_INTER_SECTOR_COOLDOWN)
            total_added += harvest_wikipedia_seeds(writer, seeds_en, "en", sector, source_tag)

        # Zwischen Phasen ebenfalls atmen
        if phase_idx < len(phases) - 1:
            print(f"  ... cooldown {WIKI_INTER_SECTOR_COOLDOWN}s vor nächster Phase ...")
            time.sleep(WIKI_INTER_SECTOR_COOLDOWN)

    elapsed = (time.time() - start) / 60
    print(f"\n=== Done: +{total_added} new docs in {elapsed:.1f} min ===")
    print(f"    Total Code-Vault: {len(writer.archive)} docs, {len(writer.cache)} embeddings")


if __name__ == "__main__":
    main()
