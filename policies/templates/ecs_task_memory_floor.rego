package proofops

import rego.v1

applies if {
    input.scope == data.proofops.scope
    input.image_digest == data.proofops.image_digest
    input.profile_hash == data.proofops.profile_hash
    input.dependency_hash == data.proofops.dependency_hash
    input.non_resize_config_hash == data.proofops.non_resize_config_hash
}

exception_applies if {
    some exception in data.proofops.exceptions
    exception.scope == input.scope
    exception.candidate_commit == input.candidate_commit
    exception.guard_revision == data.proofops.guard_revision
    exception.expires_epoch > input.reference_epoch
}

deny contains {"msg": "APPROVED_MEMORY_FLOOR_BREACH: candidate task memory is below the reviewed service floor"} if {
    applies
    is_number(input.memory_mib)
    input.memory_mib < data.proofops.minimum_task_memory_mib
    not exception_applies
}

warn contains {"msg": "TERRAFORM_VALUE_UNKNOWN: required task memory remains unresolved"} if {
    applies
    not is_number(input.memory_mib)
}

warn contains {"msg": "APPLICABILITY_CHANGED: obtain compatible evidence and separate contract review"} if {
    input.scope == data.proofops.scope
    not applies
}
