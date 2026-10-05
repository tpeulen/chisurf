"""A temporary, populated MMFDB reached through the real in-process RPC services.

MMFDB Admin is a client of the MMFDB services. Its tests, the Qt baseline capture
and the native app's screenshots all need the same realistic state: one record
of every entity the admin browses, a provenance chain, curated fluorophores with
spectra, calibrations, studies, protocols and reagent lots. This module writes
that state into a **temporary** SQLite file and gives back a client logged in as
the bootstrap administrator. The caller points the settings and the database at a
temporary folder first (:func:`use_folder`); nothing here touches ``~/.chisurf``.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The embedded desktop bootstrap creates ``admin`` (password ``admin``).
ADMIN = ("admin", "admin")


def use_folder(folder: Path, monkeypatch=None) -> Path:
    """Point the ChiSurf settings, the MMFDB settings and the database at *folder*."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    env = {
        "CHISURF_SETTINGS_DIR": str(folder),
        "MMFDB_SETTINGS_DIR": str(folder),
        "MMFDB_DATABASE_PATH": str(folder / "mmfdb.db"),
        "MMFDB_OBJECT_STORE": str(folder / "objects"),
    }
    for key, value in env.items():
        if monkeypatch is not None:
            monkeypatch.setenv(key, value)
        else:
            os.environ[key] = value
    return folder


def admin_client(login: tuple[str, str] = ADMIN):
    """An in-process MMFDB client logged in as *login* (the bootstrap admin by default)."""
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    client = MMFDBClient(inprocess=True)
    client.login(*login, quiet=True)
    return client


def _spectrum(center: float, width: float, start: float = 400.0, stop: float = 760.0):
    import math

    xs = [start + 2.0 * i for i in range(int((stop - start) / 2.0) + 1)]
    return xs, [math.exp(-0.5 * ((x - center) / width) ** 2) for x in xs]


def seed(folder: Path, client=None) -> dict:
    """Write the admin's demo state into the database of *folder*; return the ids used.

    The records match the Qt GUI interaction tests (``sample_gui``, ``exp_gui``,
    ``raw_gui`` -> ``proc_gui`` -> ``prod_gui``, ``analysis_gui`` ...) so a test of
    the native app and a test of the legacy widget talk about the same rows.
    """
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path

    folder = Path(folder)
    client = client or admin_client()
    db = MFDatabase(str(resolve_database_path()))
    try:
        users = {u.get("user_id") for u in db.get_users()}
        if "user_default" not in users:
            db.add_user("user_default", "Default User")
        if "john_doe" not in users:
            db.add_user("john_doe", "John Doe", email="john@example.org")
        db.add_device("dev_gui", "GUI Detector")
        db.add_device("mt200", "PicoQuant MT200")
        db.add_sample_condition("cond_gui", ph=7.4, temperature=298.0, buffer_composition="PBS")
        type_id = db.add_experiment_type("TCSPC", category="fluorescence")
        db.add_experiment_type("smFRET", category="single-molecule")
        db.add_sample(
            "sample_gui",
            description="GUI sample",
            sample_condition_id="cond_gui",
            measured_by_user_id="user_default",
            measured_by_device_id="dev_gui",
        )
        db.add_sample("sample_hp3", description="", measured_by_user_id="john_doe")
        db.set_sample_key_value("sample_gui", "buffer", "PBS", "initial buffer")
        db.set_sample_key_value("sample_gui", "pH", "7.4", "measured at 25 C")
        db.set_sample_key_value("sample_gui", "temperature", "298", "Kelvin")
        db.add_entity(
            "entity_gui",
            name="GUI Entity",
            sequence=["ALA", "CYS", "GLY"],
            entity_type="polymer",
            details="GUI entity details",
        )
        donor = db.add_probe(
            None,
            name="Donor GUI",
            category="organic_dye",
            description="initial donor",
            fluorophore_type="donor",
        )
        acceptor = db.add_probe(
            None,
            name="Acceptor GUI",
            category="organic_dye",
            description="initial acceptor",
            fluorophore_type="acceptor",
        )
        for probe_id, (abs_max, em_max, qy) in (
            (donor, (495.0, 519.0, 0.92)),
            (acceptor, (651.0, 671.0, 0.33)),
        ):
            db.add_optical_property(probe_id, "abs_max", abs_max, unit="nm")
            db.add_optical_property(probe_id, "em_max", em_max, unit="nm")
            db.add_optical_property(probe_id, "qy", qy, unit="")
            xs, ys = _spectrum(abs_max, 18.0)
            db.add_spectrum(probe_id, "absorption", xs, ys)
            xs, ys = _spectrum(em_max, 20.0)
            db.add_spectrum(probe_id, "emission", xs, ys)
        # A near-duplicate of the donor, for Find Duplicates.
        twin = db.add_probe(None, name="Donor-GUI", category="organic_dye", description="twin")
        db.add_optical_property(twin, "abs_max", 496.0, unit="nm")
        db.add_optical_property(twin, "em_max", 520.0, unit="nm")
        position = db.add_poly_probe_position(
            donor,
            "entity_gui",
            2,
            asym_id="A",
            residue_name="CYS",
            atom_id="CB",
            auth_name="C2",
            description="GUI label position",
        )
        db.add_sample_probe("sample_gui", donor, "donor", poly_probe_position_id=position)
        db.add_sample_probe("sample_gui", acceptor, "acceptor")
        db.add_fret_forster_radius("fr_gui", "sample_gui", donor, acceptor, 6.1, details="GUI pair")
        db.add_experiment(
            "exp_gui",
            type_id=type_id,
            sample_id="sample_gui",
            measured_by_user_id="user_default",
            measured_by_device_id="dev_gui",
            status="complete",
        )
        db.save_setup(
            setup_id="setup_gui",
            name="GUI Setup",
            configuration={"setup_type": "confocal", "details": "initial setup"},
            detectors={
                "green": {
                    "channels": [0, 1],
                    "micro_time_ranges": [[10, 90]],
                    "g_factor": 1.05,
                    "l1": 0.01,
                    "l2": 0.02,
                }
            },
            windows={"donor_excitation": [10, 90]},
            fcs_pairs={
                "green_auto": {
                    "channel_a": "green",
                    "channel_b": "green",
                    "kind": "auto",
                    "n_bins": 8,
                    "n_casc": 16,
                    "make_fine": True,
                }
            },
            created_by_user_id="user_default",
            is_public=False,
        )
        raw_path = folder / "raw_gui.ptu"
        raw_path.write_bytes(b"PTU seed data")
        processed_path = folder / "prod_gui.json"
        processed_path.write_text('{"curve": [1, 2, 3]}', encoding="utf-8")
        db.register_artifact(
            artifact_id="raw_gui",
            artifact_kind="raw_data",
            storage_mode="local_file",
            experiment_id="exp_gui",
            file_path=str(raw_path),
            validation_status="valid",
            metadata={"data_type": "tcspc"},
        )
        db.record_operation(
            operation_id="proc_gui",
            operation_type="filtering",
            experiment_id="exp_gui",
            operator_user_id="user_default",
            status="succeeded",
            settings={"threshold": 3},
        )
        db.register_artifact(
            artifact_id="prod_gui",
            artifact_kind="processed_data",
            storage_mode="local_file",
            experiment_id="exp_gui",
            file_path=str(processed_path),
            validation_status="valid",
            metadata={"processing_id": "proc_gui", "product_type": "processed_data"},
        )
        db.record_operation_link(operation_id="proc_gui", artifact_id="raw_gui", direction="input")
        db.record_operation_link(
            operation_id="proc_gui", artifact_id="prod_gui", direction="output"
        )
        db.record_operation(
            operation_id="analysis_gui",
            operation_type="local_fit",
            experiment_id="exp_gui",
            operator_user_id="user_default",
            status="succeeded",
            metadata={"model_name": "GUI Fit"},
        )
        fit_path = folder / "analysis_fit_result.json"
        fit_path.write_text('{"chi2": 1.05}', encoding="utf-8")
        db.add_analysis_parameter(
            "analysis_gui",
            "tau",
            value=3.8,
            standard_error=0.2,
            units="ns",
            parameter_type="free",
            parameter_uuid="param_gui_tau",
        )
        db.add_analysis_product(
            "analysis_gui",
            product_type="processed_data",
            storage_mode="local_file",
            processed_data_id="fit_result_gui",
            file_path=str(fit_path),
            validation_status="valid",
            metadata={"product_type": "fit_result"},
        )
        db.put_object(data=b"time,intensity\n0,10\n", filename="sample_curve.csv")
        db.record_operation(
            operation_id="ver_gui",
            operation_type="project",
            operator_user_id="user_default",
            status="succeeded",
            metadata={
                "project_id": "proj_gui",
                "project_name": "GUI Project",
                "version_number": 1,
                "description": "Project from GUI test",
            },
        )
        db.create_branch(
            branch_uuid="branch_gui",
            name="gui_branch",
            head_operation_id="ver_gui",
            created_by_user_id="user_default",
            description="GUI branch",
        )
    finally:
        db.close()

    # Workflow records go through the RPC API, the way a user would create them.
    client.create_calibration("forster_radius", 54.0, notes="Hellenkamp et al. 2018")
    client.create_calibration("forster_radius", 52.0, notes="re-measured 2026")
    client.create_calibration("g_factor", 1.05, notes="G-factor of setup_gui")
    study = client.create_study("Hairpin dynamics", description="HP3 smFRET")
    study_id = study.get("study_id") or ""
    if study_id:
        client.add_study_member(study_id, "sample", "sample_gui")
        client.set_study_field(study_id, "grant", "DFG 123")
    client.create_protocol("TCSPC acquisition", "measurement", description="Standard IRF + decay")
    client.create_protocol("Burst selection", "processing", operation_type="filtering")
    client.create_reagent_lot("fluorophore", "Alexa 488", lot_number="A488-42", vendor="Thermo")
    client.create_reagent_lot("buffer", "PBS", lot_number="PBS-7", vendor="Sigma", expiry="2031-01-01")
    client.lifecycle_transition("sample", "sample_gui", "registered", reason="received")
    client.lifecycle_transition("sample", "sample_gui", "measured", reason="TCSPC done")
    return {"sample_id": "sample_gui", "study_id": study_id, "donor": donor, "acceptor": acceptor}
