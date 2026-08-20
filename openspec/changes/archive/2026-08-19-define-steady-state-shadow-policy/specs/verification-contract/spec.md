## ADDED Requirements

### Requirement: A closed set of accepted states is asserted by equality

WHEN a constant enumerates the states a system is allowed to run in, the check
that guards it SHALL assert set equality against the intended states, not
membership of a sample. Adding a state SHALL fail that check, and removing one
SHALL fail it too.

A membership assertion passes for a superset. It therefore reports success while
testing less than it appears to, which no other rule in this spec catches: the
check was executed, and it did fail before its fix, but it does not detect the
change it exists to detect.

#### Scenario: A new accepted state is added to the constant

- **WHEN** a key is added to a constant enumerating accepted runtime states
- **THEN** the guarding check fails, so the addition has to be argued for as an
  architectural decision rather than arriving as an unnoticed entry

#### Scenario: The assertion is proved rather than assumed

- **WHEN** an exact-set assertion is introduced
- **THEN** a state is temporarily added, the check is observed to fail, the
  addition is reverted, and the guarded source file is shown to be byte-identical
  afterwards
