"""Focused offline regressions. No provider, subprocess or network imports."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest

from build_corrected_packet import build_packet, digest, semantic_support_blockers, SEMANTIC_POLICY

ROOT = Path(__file__).resolve().parent


class CorrectedPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_prompt = (ROOT / 'original-production-prompt.txt').read_text(encoding='utf-8')
        cls.original_payload = json.loads((ROOT / 'original-qualification-payload.json').read_text(encoding='utf-8'))
        cls.original_packet = json.loads(cls.original_payload['prompt'].split('\n', 1)[1])
        cls.payload, cls.packet, cls.instructions = build_packet(cls.original_prompt, cls.original_payload)
        cls.native = json.loads((ROOT.parent / 'additional-native-attempt.json').read_text(encoding='utf-8'))
        cls.audit = json.loads((ROOT.parent / 'quality-audit.json').read_text(encoding='utf-8'))
        cls.requirements = cls.packet['editorial_context']['requirements']

    def test_restores_typed_requirements_and_full_production_instructions(self):
        self.assertEqual(self.requirements, self.audit['retained_gate_components']['required_claims'])
        self.assertEqual(self.requirements[0]['kinds'], ['causal'])
        for text in self.instructions.values():
            self.assertIn(text, self.original_prompt)
            self.assertIn(text, self.payload['prompt'])
        self.assertIn('claims array must contain EXACTLY the requirements unit IDs', self.payload['prompt'])
        self.assertIn('one continuous verbatim passage', self.payload['prompt'])
        self.assertIn(SEMANTIC_POLICY, self.payload['prompt'])
        self.assertEqual(self.payload['retained_production_context_sha256'],
            '839509bbe92440be800d0c0f7ec7cd12dbe7999bd9736a2918f1c9c42789653e')

    def test_context_and_article_hash_drift_are_rejected(self):
        altered = re.sub(r'"kinds"\s*:\s*\[\s*"causal"\s*\]', '"kinds":["event"]', self.original_prompt)
        self.assertTrue(altered != self.original_prompt, 'Required-kind mutation was applied')
        with self.assertRaisesRegex(ValueError, 'context hash mismatch'):
            build_packet(altered, self.original_payload)
        payload = copy.deepcopy(self.original_payload)
        packet = copy.deepcopy(self.original_packet)
        packet['article']['title'] += ' altered'
        payload['prompt'] = payload['prompt'].split('\n', 1)[0] + '\n' + json.dumps(packet)
        with self.assertRaisesRegex(ValueError, 'Changed article'):
            build_packet(self.original_prompt, payload)

    def test_same_article_evidence_probes_schema_and_bounded_sources(self):
        for key in ['article', 'evidence', 'qualification_probes']:
            self.assertEqual(self.packet[key], self.original_packet[key])
        self.assertEqual(self.payload['schema'], self.original_payload['schema'])
        self.assertEqual(digest(self.packet['article']), self.payload['article_canonical_sha256'])
        self.assertEqual(digest(self.packet['editorial_context']), self.payload['compact_editorial_context_sha256'])
        self.assertNotEqual(self.payload['compact_editorial_context_sha256'], self.payload['retained_production_context_sha256'])

    def test_literal_title_date_and_self_pass_cannot_replace_causal_support(self):
        output = self.native['output']
        audit = self.audit['causal_audit']
        self.assertTrue(output['review']['passed'])
        self.assertTrue(all(p['reject'] for p in output['probe_results']))
        self.assertTrue(audit['quote_continuous_in_original_page'])
        self.assertTrue(audit['quote_continuous_in_supplied_excerpts'])
        claim = audit['actual_claim_row']
        self.assertEqual(output['review']['editorial_audit']['claims'], [claim])
        # This is the retained independent assessment of the ACTUAL output,
        # not a keyword classifier or synthetic corrected model response.
        assessment = {audit['unit_id']: {'binding_sha256': digest({
            'requirement': self.requirements[0], 'claim': claim}), 'passed': audit['passed']}}
        blockers = semantic_support_blockers(output, self.requirements, assessment)
        self.assertIn(audit['unit_id'] + ': independent semantic support failed', blockers)
        self.assertEqual(self.audit['status'], 'quality_hold')

    def test_absent_or_mismatched_independent_assessment_fails_closed(self):
        output = self.native['output']
        self.assertTrue(semantic_support_blockers(output, self.requirements, {}))
        assessment = {self.requirements[0]['id']: {'binding_sha256': 'other-output', 'passed': True}}
        self.assertTrue(semantic_support_blockers(output, self.requirements, assessment))
        duplicate = copy.deepcopy(output)
        duplicate['review']['editorial_audit']['claims'] *= 2
        self.assertIn('Claims must match the exact required unit IDs once each',
            semantic_support_blockers(duplicate, self.requirements, {}))

    def test_unexecuted_new_packet_cannot_reuse_consumed_trial(self):
        self.assertEqual(hashlib.sha256((ROOT / 'corrected-prompt.txt').read_bytes()).hexdigest(),
            self.payload['input_hashes']['prompt.txt'])
        stored = json.loads((ROOT / 'corrected-payload.json').read_text(encoding='utf-8'))
        self.assertEqual(stored, self.payload)
        self.assertEqual(self.payload['status'], 'offline_prepared_not_executed')
        self.assertIs(self.payload['execution_authorized'], False)
        self.assertEqual(self.payload['approved_cli_starts_remaining'], 0)
        self.assertNotEqual(self.payload['job_id'], self.native['receipt']['job_id'])
        self.assertNotEqual(self.payload['input_hashes']['prompt.txt'], self.native['receipt']['input_hashes']['prompt.txt'])
        self.assertEqual(hashlib.sha256(self.original_payload['prompt'].encode('utf-8')).hexdigest(),
            self.native['receipt']['input_hashes']['prompt.txt'])
        seal = json.loads((ROOT.parent / 'additional-terminal-seal-proof.json').read_text(encoding='utf-8'))
        self.assertEqual(seal['state']['status'], 'qualification_quality_hold')
        self.assertTrue(seal['state']['qualification_allowance_consumed'])
        self.assertTrue(seal['native_receipt_unchanged'])
        self.assertTrue(seal['new_nonce_unchanged'])
        self.assertTrue(seal['previous_sealed_trial_unchanged'])
        self.assertEqual(seal['additional_model_turns'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
