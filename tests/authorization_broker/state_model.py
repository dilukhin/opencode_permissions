"""Pure test-only broker authorization state model for Gate B."""
from dataclasses import dataclass


class BrokerContractError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass
class Grant:
    authorization_id: str
    operation_identity: str
    source_binding: tuple
    broker_generation: int
    host_registration_generation: int
    provenance: str
    state: str


class BrokerStateModel:
    def __init__(self):
        self.broker_generation = 1
        self.host_registration_generation = 1
        self.trusted_host_peer = "host-peer"
        self.trusted_pep_peer = "pep-peer"
        self.host_live = True
        self.active_sources = set()
        self.grants = {}
        self._next = 1

    def request(self, caller_peer, operation_identity, source_binding, policy_decision="ASK_USER"):
        if caller_peer != self.trusted_host_peer:
            raise BrokerContractError("UNTRUSTED_HOST")
        if not self.host_live:
            raise BrokerContractError("HOST_NOT_LIVE")
        if policy_decision == "DENY":
            raise BrokerContractError("HARD_DENY_NO_GRANT")
        if policy_decision not in ("ASK_USER", "ALLOW"):
            raise BrokerContractError("INVALID_POLICY_DECISION")

        authorization_id = f"a{self._next}"
        self._next += 1
        state = "PENDING" if policy_decision == "ASK_USER" else "APPROVED"
        provenance = "user_once" if policy_decision == "ASK_USER" else "policy_allow"
        grant = Grant(
            authorization_id,
            operation_identity,
            tuple(source_binding),
            self.broker_generation,
            self.host_registration_generation,
            provenance,
            state,
        )
        self.grants[authorization_id] = grant
        self.active_sources.add(tuple(source_binding))
        return authorization_id

    def approve_once(self, authorization_id):
        grant = self.grants.get(authorization_id)
        if grant is None:
            raise BrokerContractError("GRANT_NOT_FOUND")
        if grant.state != "PENDING":
            raise BrokerContractError("GRANT_NOT_PENDING")
        grant.state = "APPROVED"

    def consume(self, caller_peer, authorization_id, operation_identity, source_binding):
        if caller_peer != self.trusted_pep_peer:
            raise BrokerContractError("UNTRUSTED_PEP")
        grant = self.grants.get(authorization_id)
        if grant is None:
            raise BrokerContractError("GRANT_NOT_FOUND")
        if grant.state == "CONSUMED":
            raise BrokerContractError("GRANT_ALREADY_CONSUMED")
        if grant.state != "APPROVED":
            raise BrokerContractError("GRANT_NOT_APPROVED")
        if grant.broker_generation != self.broker_generation:
            raise BrokerContractError("BROKER_GENERATION_MISMATCH")
        if grant.host_registration_generation != self.host_registration_generation:
            raise BrokerContractError("HOST_GENERATION_MISMATCH")
        if not self.host_live:
            raise BrokerContractError("HOST_NOT_LIVE")

        source = tuple(source_binding)
        if source != grant.source_binding:
            raise BrokerContractError("SOURCE_BINDING_MISMATCH")
        if source not in self.active_sources:
            raise BrokerContractError("SOURCE_NOT_ACTIVE")
        if operation_identity != grant.operation_identity:
            raise BrokerContractError("OPERATION_IDENTITY_MISMATCH")

        grant.state = "CONSUMED"
        return "ALLOW_EXECUTION_ONCE"

    def abort_source(self, source_binding):
        self.active_sources.discard(tuple(source_binding))

    def host_exit(self):
        self.host_live = False

    def broker_restart(self):
        self.broker_generation += 1
        self.grants.clear()
        self.active_sources.clear()
