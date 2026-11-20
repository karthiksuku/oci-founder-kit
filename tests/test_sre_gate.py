"""Synthetic protected-verifier and production refusal tests. No cloud clients."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sre_gate as gate
import sre_scan as scanner

class SignedCandidate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.app = self.tmp / "app"
        self.app.mkdir()
        self.p = p = gate.project_module()
        e = p.helper("environments")
        now = self.now = int(time.time())
        self.image = "sha256:" + "3" * 64
        self.plan = hashlib.sha256(b"test candidate").hexdigest()
        for name in ("stage", "live"):
            (self.app / "deploy" / name).mkdir(parents=True)
            (self.app / "deploy" / name / "main.tf").write_text("# replay fixture")
        (self.app / ".gitignore").write_text(".oci-kit/\n.gate/\n")
        with p.Store(self.app, create=True, write=True) as store:
            store.save({"schema": p.SCHEMA, "task": "build", "mode": "existing", "agent": "both",
                        "stack": "custom", "blueprint": None, "project_identity": p.identity(store.root_fd),
                        "created_at": now, "observed_at": now, "source_sha256": p.source_fingerprint(store.root_fd),
                        "kit_sha256": p.kit_fingerprint(), "records": {}})
        for name, role in (("stage","rehearsal"), ("live","production")):
            e.create(self.app, name=name, role=role, blueprint="fullstack-container", infrastructure="deploy/" + name,
                     target={"image_digest": self.image, "compartment_id":"ocid1.compartment.oc1..test"+name},
                     backend={"region":"us-phoenix-1","namespace":"testnamespace","bucket":"private-state-test",
                              "key": name+"/state.tfstate","workspace_key_prefix": name+"/workspaces"})
        with p.Store(self.app, environment="live") as store:
            cfg = store.environment_config
            self.evidence = self.app / ".oci-kit/environments/live/evidence"
        saved = self.app / "deploy/live/.gate"
        saved.mkdir(mode=0o700)
        self.save(saved/"tfplan", b"test candidate")
        self.summary = {"kind":"apply", "created_at_epoch":now-1,"expires_at_epoch":now+150,
                        "plan_sha256":self.plan,"project_environment":{"role":"production","component_role":"web",
                         "environment":"live","configuration_sha256":p.digest(p.canonical(cfg))},
                        "workload_proof":{"schema":"oci-named-workload-proof/1","image_digest":self.image}}
        self.save(saved/"plan-summary.json", self.summary)
        for args in (["init","-q"],["add","."],["-c","user.email=fixture@example.invalid","-c","user.name=fixture",
                                             "commit","-qm","candidate"]):
            subprocess.run(["/usr/bin/git","-C",str(self.app),*args],check=True,capture_output=True)
        self.key = self.tmp / "key"
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True)
        self.patch(mock.patch.object(gate, "trusted_key", return_value=b" ".join(self.key.with_suffix(".pub").read_bytes().split()[:2])))
        # The independently tested bound OCI receipt reader is the only mocked cloud-facing dependency.
        real = p.helper
        def helper(name):
            if name == "operations":
                return mock.Mock(receipt_at=mock.Mock(return_value=({}, "1"*64)))
            return real(name)
        self.patch(mock.patch.object(p, "helper", side_effect=helper))
        self.patch(mock.patch.object(gate, "project_module", return_value=p))
        self.journey = self.app/".oci-kit/environments/stage/sre-journey.json"
        self.declaration = {"schema":"oci-sre-journey/1","journey":"check-record","assertions":["The synthetic record survives reload"]}
        self.save(self.journey, self.declaration)
        self.binding = self.check()["binding"]

    def patch(self, patched):
        value = patched.start()
        self.addCleanup(patched.stop)
        return value

    def save(self,path,value):
        path.write_bytes(value if isinstance(value,bytes) else self.p.canonical(value))
        path.chmod(0o600)

    def check(self, **changes):
        params = dict(environment="live", rehearsal="stage", plan_sha256=self.plan)
        params.update(changes)
        return gate.request(self.app, **params)

    def observations(self):
        controls={}
        for name in gate.profile_controls("taskboard"):
            metrics = {k:True for k in gate.REQUIRED.get(name, ())}
            if name == "restore":
                metrics.update(recovery_seconds=42, data_age_seconds=12)
            if name == "security_scan":
                metrics = {"schema":"oci-sre-scan/2", "image_digest":self.image,
                           "source_revision":self.binding["source_revision"], "scanner_version":scanner.VERSION,
                           "scanner_sha256":scanner.BINARY, "observed_at":self.now, "database_updated_at":self.now,
                           "database_schema":2, "os_eol":False, "sbom_digest":"sha256:"+"7"*64, "counts":{
                               n:int(n in ("terraform_checks","dockerfile_checks","os_packages","runtime_packages","production_lock_packages"))
                               for n in scanner.COUNTS}}
            if name == "oci_registry_scan":
                metrics = {"schema":"oci-sre-registry-scan/1", "image_digest":self.image, "digest_verified":True,
                           "compartment_repository_verified":True,"observed_at":self.now,"finished_at":self.now,
                           "problem_count":0,"severity":"NONE"}
            controls[name] = {"observations":metrics,"observed_at":self.now,"artifact_sha256":"0"*64}
        return controls

    def deliver(self,controls,alter=None):
        payload = {"schema":gate.SCHEMA,"issued_at":self.now,"controls":controls,"binding":self.binding}
        if alter: alter(payload)
        file=self.evidence/("sre-"+self.plan+".json")
        self.save(file, payload)
        sig=self.evidence/("sre-"+self.plan+".sig")
        subprocess.run(["/usr/bin/ssh-keygen","-q","-Y","sign","-f",str(self.key),"-n",gate.NAMESPACE],
                       input=file.read_bytes(),stdout=(capture:=tempfile.TemporaryFile()),check=True)
        capture.seek(0); self.save(sig,capture.read()); capture.close()

    def test_signed_controls_pass_but_are_not_approval(self):
        self.deliver(self.observations())
        result=self.check()
        self.assertEqual(result["status"],"passed", result)
        self.assertFalse(result["approval_granted"])
        self.assertEqual(self.check(rehearsal=None)["attestation_sha256"],result["attestation_sha256"])

    def test_absent_stale_critical_or_failed_controls_do_not_pass(self):
        self.assertEqual(self.check()["status"],"blocked")
        for key,edit in (("performance",lambda r:r["observations"].update(latency_target_met=False)),
                         ("restore",lambda r:r.update(observed_at=self.now-86401)),
                         ("security_scan",lambda r:r["observations"]["counts"].update(critical=1)),
                         ("oci_registry_scan",lambda r:r["observations"].update(severity="HIGH",problem_count=1)),
                         ("monitoring_drill",lambda r:r["observations"].pop("primary_received"))):
            rows=self.observations();edit(rows[key]);self.deliver(rows)
            result=self.check()
            self.assertEqual(result["status"],"blocked",key)
            self.assertNotEqual(next(x for x in result["checks"] if x["id"]==key)["status"],"passed")

    def test_signed_wrong_binding_forged_bytes_and_changed_source_fail(self):
        for k,v in (("rehearsal","other"),("plan_sha256","0"*64),("image_digest","sha256:"+"0"*64),
                    ("policy","old"),("production_sha256","3"*64)):
            self.deliver(self.observations(),lambda x:x.update(binding=dict(self.binding,**{k:v})))
            self.assertEqual(self.check()["status"],"blocked",k)
        self.deliver(self.observations())
        f=self.evidence/("sre-"+self.plan+".json")
        self.save(f, f.read_bytes()+b' ')
        self.assertEqual(self.check()["status"],"blocked")
        self.deliver(self.observations());(self.app/"deploy/stage/main.tf").write_text("# changed")
        self.assertEqual(self.check()["status"],"blocked")

    def test_private_assertions_bind_decision_without_disclosing_them(self):
        self.deliver(self.observations())
        verdict = self.check()
        self.assertEqual(verdict["status"],"passed")
        self.assertEqual(verdict["binding"]["journey_sha256"],self.p.digest(self.p.canonical(self.declaration)))
        self.assertNotIn(self.declaration["assertions"][0],json.dumps(verdict))
        self.save(self.journey,dict(self.declaration,assertions=["Ensure another user cannot view it"]))
        self.assertEqual(self.check()["status"],"blocked")
        self.journey.unlink()
        self.assertNotIn("binding",self.check())
        self.assertIn("critical_journey",[c["id"] for c in self.check()["checks"]])

    def test_assembly_verifies_raw_artifacts_and_control_binding(self):
        challenge=self.tmp/"challenge";self.save(challenge,self.check());directory=self.tmp/"proof";directory.mkdir()
        for key,row in self.observations().items():
            raw=(key+" results").encode()
            self.save(directory/(key+".artifact"),raw)
            self.save(directory/(key+".json"),{"schema":"oci-sre-control/1","id":key,"observed_at":self.now,
                      "binding_sha256":self.p.digest(self.p.canonical(self.binding)), "observations":row["observations"],
                      "raw_artifact_sha256":gate.digest(raw)})
        gate.assemble(challenge,directory,self.tmp/"candidate")
        self.assertEqual(json.loads((self.tmp/"candidate").read_bytes())["schema"],gate.SCHEMA)
        self.save(directory/"restore.artifact",b"unrelated")
        with self.assertRaises(ValueError):
            gate.assemble(challenge,directory,self.tmp/"candidate2")

    def test_low_level_gate_rechecks_policy_and_keeps_bootstrap_independent(self):
        module=self.p.helper("readiness").load("skills/oci-deploy/scripts/deploy_gate.py")
        with self.assertRaises(module.GateRefused):
            module.require_sre(self.app,None,{"kind":"apply","resources":[{"type":"oci_container_instances_container_instance"}]},self.plan)
        self.assertIsNone(module.require_sre(self.app,None,{"kind":"apply","resources":[{"type":"oci_objectstorage_bucket"}]},self.plan))
        self.assertIsNone(module.require_sre(self.app,{"role":"production"},{"kind":"destroy"},self.plan))
        self.assertIsNone(module.require_sre(self.app,{"role":"rehearsal"},{"kind":"apply"},self.plan))
        selected={"role":"production","component_role":"web","project_path":str(self.app),"environment":"live"}
        with self.assertRaises(module.GateRefused):
            module.require_sre(self.app,selected,self.summary,self.plan)


class ApplyBoundary(unittest.TestCase):
    def test_unbound_workload_cannot_enter_apply(self):
        from test_deploy_gate import GateTestCase, PLAN
        fixture = GateTestCase()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        plan = dict(PLAN, resource_changes=[{"address":"oci_container_instances_container_instance.web",
                    "type":"oci_container_instances_container_instance","name":"web","change":{"actions":["create"]}}])
        fixture.write_json("plan.json", plan)
        summary, _ = fixture.plan()
        code, _, error = fixture.apply(summary["plan_sha256"])
        self.assertNotEqual(code, 0); self.assertIn("explicitly bound target", error)
        self.assertFalse(fixture.applied())
        self.assertTrue((fixture.gate_dir/"tfplan").exists())

    def test_changed_eligibility_after_plan_consumption_stops_before_apply(self):
        from test_deploy_gate import GateTestCase, gate as deploy
        fixture = GateTestCase()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        summary, _ = fixture.plan()
        with mock.patch.object(deploy, "require_sre", side_effect=["1"*64, deploy.GateRefused("Recheck failed")]) as check:
            code, _, error = fixture.apply(summary["plan_sha256"])
        self.assertNotEqual(code, 0)
        self.assertEqual(check.call_count, 2)
        self.assertTrue(check.call_args.kwargs["evaluated"])
        self.assertFalse(fixture.applied())
        self.assertFalse((fixture.gate_dir/"tfplan").exists())
        receipt = json.loads(fixture.receipts()[0].read_bytes())
        self.assertFalse(receipt["apply_started"])
        self.assertEqual(receipt["status"], "refused")


class IndependentResults(unittest.TestCase):
    def test_junit_requires_individual_outcomes_and_rejects_skips(self):
        import sre_results
        checks = gate.REQUIRED["browser_journey"]
        raw = ("<testsuite>"+"".join(f'<testcase name="{c}"/>' for c in checks)+"</testsuite>").encode()
        self.assertEqual(sre_results.junit(raw,"browser_journey"),dict.fromkeys(checks,True))
        for wrong in (raw.replace(b"reload_persistence",b"irrelevant"), raw.replace(b"/></testsuite>",b"><skipped/></testcase></testsuite>"),
                      raw.replace(b"</testsuite>",b'<testcase name="main_action"/></testsuite>'),
                      raw.replace(b"<testsuite>",b'<testsuite failures="1">')):
            with self.assertRaises(ValueError):
                sre_results.junit(wrong,"browser_journey")


class NamedProductionJourney(unittest.TestCase):
    def test_rehearsal_receipt_to_exact_signed_named_apply_with_fake_terraform(self):
        """Use the real environment/receipt/plan readers; only Terraform and trust enrollment substitute."""
        import shutil
        from test_environment_gate import EnvironmentGate, BACKEND, TARGET, binding
        fixture=EnvironmentGate()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        p=gate.project_module()
        # The project root and both source stacks are committed before the signed candidate.
        prod=fixture.project/"live"
        shutil.copytree(fixture.stack,prod)
        target=dict(TARGET,compartment_id="ocid1.compartment.oc1..live",origin="https://live.example.invalid")
        backend=dict(BACKEND,key="live/app.tfstate",workspace_key_prefix="live/workspaces")
        fixture.env.create(fixture.project,name="live",role="production",infrastructure="live",
                           target=target,backend={k:backend[k] for k in binding.BACKEND_FIELDS})
        (fixture.project/".gitignore").write_text(".oci-kit/\n.gate/\n.terraform/\n")
        (fixture.project/"package.json").write_text('{"dependencies":{"next":"16.0.0"}}')
        with p.Store(fixture.project, environment="rehearsal", write=True) as store:
            fixture.env.put(store.fd,"sre-journey.json",p.canonical({"schema":"oci-sre-journey/1","journey":"view-record",
                            "assertions":["The migrated record loads"]}))
            fixture.env.put(store.fd,"application.json",p.canonical({"schema":"oci-kit-application/1","recipe":"nextjs",
                "app_directory":".","port":8080,"health_path":"/healthz","commands":{k:[k] for k in ("build","start","test")},
                "dependencies":[],"background_work":"source","probe_runtime":"node","base_image":"node@sha256:"+"a"*64}))
        for args in (["init","-q"],["add","."],["-c","user.email=fixture@example.invalid","-c","user.name=fixture","commit","-qm","candidate"]):
            subprocess.run(["/usr/bin/git","-C",str(fixture.project),*args],check=True,capture_output=True)
        fixture.write_json("state.json",{"values":{"root_module":{"resources":[{
            "address":"oci_container_instances_container_instance.app","type":"oci_container_instances_container_instance",
            "mode":"managed","name":"app","values":{"id":"ocid1.computecontainerinstance.oc1.test.synthetic",
                                                     "compartment_id":TARGET["compartment_id"]}}]}}})
        stage=fixture.resource_plan()
        self.assertEqual(fixture.apply(stage["plan_sha256"])[0],0)
        # Select new destination explicitly, using the exact same image.
        fixture.stack=prod
        fixture.config.write_text(json.dumps(backend))
        tree=(fixture.tmp/"plan.json").read_text().replace(TARGET["compartment_id"],target["compartment_id"]).replace(TARGET["origin"],target["origin"])
        fixture.write_json("plan.json",json.loads(tree))
        for operation in ("init","plan"):
            extra=["--backend-config",str(fixture.config)] if operation=="init" else []
            code,_,err=fixture.run_gate("backend-plan","--dir",str(prod),"--operation",operation,"--project",str(fixture.project),
                                        "--environment","live",*extra)
            self.assertEqual(code,0,err)
            code,_,err=fixture.execute()
            self.assertEqual(code,0,err)
        summary=json.loads((prod/".gate/plan-summary.json").read_text())
        self.plan=summary["plan_sha256"];self.p=p;self.now=int(time.time());self.image=target["image_digest"]
        self.key=fixture.tmp/"verifier"
        subprocess.run(["/usr/bin/ssh-keygen","-q","-t","ed25519","-N","","-f",str(self.key)],check=True)
        self.evidence=fixture.project/".oci-kit/environments/live/evidence"
        r=gate.request(fixture.project,environment="live",rehearsal="rehearsal",plan_sha256=self.plan)
        self.assertIn("binding",r,r)
        self.assertEqual(r["binding"]["profile"],"hosting-first-nextjs")
        self.binding=r["binding"]
        controls=SignedCandidate.observations(self)
        for name in gate.MIGRATION:
            controls[name]={"observed_at":self.now,"artifact_sha256":"e"*64,"observations":dict.fromkeys(gate.REQUIRED[name],True)}
        self.save=lambda path,value:SignedCandidate.save(self,path,value)
        SignedCandidate.deliver(self,controls)
        pub=b" ".join(self.key.with_suffix(".pub").read_bytes().split()[:2])
        with mock.patch.object(gate,"trusted_key",return_value=pub):
            r=gate.request(fixture.project,environment="live",rehearsal="rehearsal",plan_sha256=self.plan)
            self.assertEqual(r["status"],"passed",r)
            # Low-level helper otherwise loads isolated copies of the same gate from disk.
            helper=p.helper
            p.helper=lambda key: gate if key=="sre_gate" else helper(key)
            with mock.patch.object(binding,"modules",return_value=(fixture.env,p)):
                code,_,err=fixture.apply(self.plan)
                self.assertEqual(code,0,err)
        receipt=json.loads(fixture.receipts()[0].read_text())
        self.assertEqual(receipt["sre_attestation_sha256"],r["attestation_sha256"])
