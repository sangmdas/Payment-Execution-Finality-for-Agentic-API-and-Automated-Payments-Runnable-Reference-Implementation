from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from dataclasses import replace

from payment_finality.canonical import canonical_json, digest_instruction, normalize_amount
from payment_finality.demo import build_demo, sample_instruction
from payment_finality.errors import Code, FinalityError
from payment_finality.models import PaymentInstruction, PolicySnapshot, utc_now
from payment_finality.rail import DefiniteRailFailure, UnknownRailResult
from payment_finality.store import SQLiteFinalityStore


class DefiniteFailRail:
    def post(self, instruction, authority_id):
        raise DefiniteRailFailure("rejected before posting")


class UnknownFailRail:
    def post(self, instruction, authority_id):
        raise UnknownRailResult("timeout after submit")


class CanonicalizationTests(unittest.TestCase):
    def test_amount_eur_integer(self): self.assertEqual(normalize_amount("150", "EUR"), "150.00")
    def test_amount_eur_one_decimal(self): self.assertEqual(normalize_amount("150.0", "EUR"), "150.00")
    def test_amount_eur_two_decimals(self): self.assertEqual(normalize_amount("150.00", "EUR"), "150.00")
    def test_amount_jpy_zero_scale(self): self.assertEqual(normalize_amount("150", "JPY"), "150")
    def test_amount_kwd_three_scale(self): self.assertEqual(normalize_amount("1.2", "KWD"), "1.200")
    def test_reject_negative(self): self._reject("-1", "EUR")
    def test_reject_zero(self): self._reject("0", "EUR")
    def test_reject_excess_scale(self): self._reject("1.001", "EUR")
    def test_reject_nan(self): self._reject("NaN", "EUR")
    def test_reject_infinity(self): self._reject("Infinity", "EUR")
    def test_reject_plus_sign(self): self._reject("+1", "EUR")

    def _reject(self, amount, currency):
        with self.assertRaises(FinalityError): normalize_amount(amount, currency)

    def test_canonical_key_order(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_equivalent_amounts_same_digest(self):
        a = sample_instruction()
        b = replace(a, amount="150.00")
        self.assertEqual(digest_instruction(a), digest_instruction(b))

    def test_metadata_is_non_load_bearing(self):
        a = sample_instruction()
        b = replace(a, metadata={"trace": "different"})
        self.assertEqual(digest_instruction(a), digest_instruction(b))

    def test_cross_language_vector(self):
        path = Path(__file__).parents[1] / "test-vectors" / "ef-pay-1.json"
        vector = json.loads(path.read_text(encoding="utf-8"))
        instruction = PaymentInstruction(**vector["instruction"], sink_id="core-post-eu-1")
        normalized = normalize_amount(instruction.amount, instruction.currency)
        self.assertEqual(normalized, vector["expected_normalized_amount"])
        from payment_finality.canonical import instruction_projection
        self.assertEqual(canonical_json(instruction_projection(instruction, normalized)).decode(), vector["expected_canonical_utf8"])
        self.assertEqual(digest_instruction(instruction, normalized), vector["expected_digest"])


class FinalityFlowTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.store, self.ped, self.sink, self.rail = build_demo()
        self.instruction = sample_instruction()

    def issue(self, instruction=None):
        instruction = instruction or self.instruction
        act = self.ped.prepare(instruction)
        evidence, authority = self.ped.validate_and_issue(act)
        return act, evidence, authority

    def assert_denied_without_post(self, code, live=None, authority=None):
        if authority is None:
            _, _, authority = self.issue()
        with self.assertRaises(FinalityError) as caught:
            self.sink.verify_and_post(live or self.instruction, authority)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(len(self.rail.posts), 0)

    def test_allow_posts_once(self):
        _, _, authority = self.issue()
        self.assertEqual(self.sink.verify_and_post(self.instruction, authority), "settlement-1")
        self.assertEqual(self.store.state(authority.authority_id), "POSTED")

    def test_replay_same_authority_denied(self):
        _, _, authority = self.issue()
        self.sink.verify_and_post(self.instruction, authority)
        with self.assertRaises(FinalityError) as caught:
            self.sink.verify_and_post(self.instruction, authority)
        self.assertEqual(caught.exception.code, Code.AUTHORITY_ALREADY_USED)
        self.assertEqual(len(self.rail.posts), 1)

    def test_second_authority_same_digest_denied(self):
        _, _, first = self.issue()
        _, _, second = self.issue()
        self.sink.verify_and_post(self.instruction, first)
        with self.assertRaises(FinalityError) as caught:
            self.sink.verify_and_post(self.instruction, second)
        self.assertEqual(caught.exception.code, Code.REPLAY_DETECTED)
        self.assertEqual(len(self.rail.posts), 1)

    def test_amount_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, amount="1500.00"))

    def test_currency_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, currency="USD"))

    def test_beneficiary_id_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, beneficiary_id="attacker-992"))

    def test_beneficiary_account_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, beneficiary_account_ref="acct-attacker"))

    def test_rail_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, rail_id="ACH"))

    def test_purpose_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, purpose_id="payroll"))

    def test_mandate_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, mandate_id="other"))

    def test_invoice_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, invoice_ref="INV-ATTACK"))

    def test_agent_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, agent_id="ap-agent-2"))

    def test_workload_substitution(self):
        self.assert_denied_without_post(Code.INSTRUCTION_SUBSTITUTION, replace(self.instruction, workload_id="spiffe://evil/workload"))

    def test_sink_substitution(self):
        self.assert_denied_without_post(Code.SINK_MISMATCH, replace(self.instruction, sink_id="psp-alt-2"))

    def test_tampered_authority(self):
        _, _, authority = self.issue()
        altered_scope = dict(authority.scope)
        altered_scope["amount"] = "1.00"
        self.assert_denied_without_post(Code.INVALID_AUTHORITY, authority=replace(authority, scope=altered_scope))

    def test_tampered_signature(self):
        _, _, authority = self.issue()
        self.assert_denied_without_post(Code.INVALID_AUTHORITY, authority=replace(authority, signature="invalid"))

    def test_expired_authority(self):
        _, _, authority = self.issue()
        with self.assertRaises(FinalityError) as caught:
            self.sink.verify_and_post(self.instruction, authority, now=authority.expires_at)
        self.assertEqual(caught.exception.code, Code.EXPIRED_AUTHORITY)

    def test_policy_epoch_advance(self):
        _, _, authority = self.issue()
        self.policy.snapshot = PolicySnapshot(13, 4, 7)
        self.assert_denied_without_post(Code.EPOCH_MISMATCH, authority=authority)

    def test_revocation_epoch_advance(self):
        _, _, authority = self.issue()
        self.policy.snapshot = PolicySnapshot(12, 5, 7)
        self.assert_denied_without_post(Code.EPOCH_MISMATCH, authority=authority)

    def test_risk_epoch_advance(self):
        _, _, authority = self.issue()
        self.policy.snapshot = PolicySnapshot(12, 4, 8)
        self.assert_denied_without_post(Code.EPOCH_MISMATCH, authority=authority)

    def test_blocked_beneficiary_denied_at_ped(self):
        self.policy.blocked_beneficiaries.add("vendor-441")
        with self.assertRaises(FinalityError) as caught:
            self.issue()
        self.assertEqual(caught.exception.code, Code.PAYEE_BLOCKED)

    def test_mandate_miss_denied_at_ped(self):
        with self.assertRaises(FinalityError) as caught:
            self.issue(replace(self.instruction, mandate_id="missing"))
        self.assertEqual(caught.exception.code, Code.MANDATE_MISS)

    def test_amount_envelope_denied_at_ped(self):
        with self.assertRaises(FinalityError) as caught:
            self.issue(replace(self.instruction, amount="5000.00"))
        self.assertEqual(caught.exception.code, Code.AMOUNT_ENVELOPE)

    def test_unpermitted_rail_denied_at_ped(self):
        with self.assertRaises(FinalityError) as caught:
            self.issue(replace(self.instruction, rail_id="ACH"))
        self.assertEqual(caught.exception.code, Code.RAIL_MISMATCH)

    def test_unpermitted_purpose_denied_at_ped(self):
        with self.assertRaises(FinalityError) as caught:
            self.issue(replace(self.instruction, purpose_id="payroll"))
        self.assertEqual(caught.exception.code, Code.PURPOSE_MISMATCH)

    def test_missing_holder_denied_at_ped(self):
        with self.assertRaises(FinalityError) as caught:
            self.issue(replace(self.instruction, agent_id="", workload_id=""))
        self.assertEqual(caught.exception.code, Code.HOLDER_MISMATCH)

    def test_missing_evidence_denied(self):
        _, _, authority = self.issue()
        self.store._conn.execute("PRAGMA foreign_keys=OFF")
        self.store._conn.execute("DELETE FROM evidence WHERE evidence_id=?", (authority.evidence_id,))
        self.assert_denied_without_post(Code.EVIDENCE_MISSING, authority=authority)

    def test_definite_rail_failure_marks_terminal(self):
        _, _, authority = self.issue()
        self.sink.rail = DefiniteFailRail()
        with self.assertRaises(DefiniteRailFailure):
            self.sink.verify_and_post(self.instruction, authority)
        self.assertEqual(self.store.state(authority.authority_id), "FAILED_DEFINITE")

    def test_unknown_rail_failure_stays_pending(self):
        _, _, authority = self.issue()
        self.sink.rail = UnknownFailRail()
        with self.assertRaises(FinalityError) as caught:
            self.sink.verify_and_post(self.instruction, authority)
        self.assertEqual(caught.exception.code, Code.RAIL_RESULT_UNKNOWN)
        self.assertEqual(self.store.state(authority.authority_id), "CONSUMED_PENDING")

    def test_concurrent_consume_exactly_one_post(self):
        _, _, authority = self.issue()
        outcomes = []
        barrier = threading.Barrier(2)
        def worker():
            barrier.wait()
            try:
                outcomes.append(self.sink.verify_and_post(self.instruction, authority))
            except Exception as exc:
                outcomes.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(isinstance(x, str) for x in outcomes), 1)
        self.assertEqual(len(self.rail.posts), 1)

    def test_file_store_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/finality.db"
            first = SQLiteFinalityStore(path)
            first.close()
            second = SQLiteFinalityStore(path)
            self.assertIsNone(second.state("unknown"))
            second.close()

    def test_evidence_committed_before_authority(self):
        _, evidence, authority = self.issue()
        self.assertIsNotNone(self.store.evidence_payload(evidence.evidence_id))
        self.assertEqual(authority.evidence_id, evidence.evidence_id)

    def test_candidate_is_non_effective(self):
        act = self.ped.prepare(self.instruction)
        self.assertEqual(act.status, "NON_EFFECTIVE")
        self.assertEqual(len(self.rail.posts), 0)

    def test_authority_is_sink_bound(self):
        _, _, authority = self.issue()
        self.assertEqual(authority.binding["finality_sink_id"], "core-post-eu-1")

    def test_authority_is_nonce_bound(self):
        act, _, authority = self.issue()
        self.assertEqual(authority.binding["nonce"], act.nonce)

    def test_authority_is_single_use(self):
        _, _, authority = self.issue()
        self.assertTrue(authority.single_use)

    def test_authority_is_digest_bound(self):
        act, evidence, authority = self.issue()
        self.assertEqual(authority.binding["instruction_digest"]["value"], act.instruction_digest)
        self.assertEqual(evidence.instruction_digest, act.instruction_digest)


if __name__ == "__main__":
    unittest.main()
