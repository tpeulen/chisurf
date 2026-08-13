Development
===========

Internal engineering documentation for ChiSurf maintainers and contributors:
software architecture, the client/server (ZMQ / JSON-RPC) design, the metadata /
provenance database (MMFDB) design notes and reviews, product-requirement
documents (PRDs), the Python API reference, and release/CI process notes.

.. note::

   These pages describe *how ChiSurf is built*, not how to use it. For usage see
   :doc:`Guides </guides/index>` and :doc:`Concepts </concepts/index>`. These
   documents are working notes and design records.

Architecture & API
------------------

.. toctree::
   :maxdepth: 1

   documentation_maintenance
   architecture
   architecture_client_server
   architecture_mvc_actions
   dialogs_and_progress
   ui_data_scheme
   chimol_widget_toolkit
   plugin_architecture
   proxy_rpc_design
   history_project_mcp
   client_server_migration_plan
   client_server_next_steps
   client_server_agent_entrypoint
   api
   parameter_registry_tools
   benchmarks

MMFDB / database design
-----------------------

.. toctree::
   :maxdepth: 1

   prd_mmfdb_architecture
   prd_mmfdb_auth_rights
   prd_mmfdb_viewer_node_editor_workflows
   prd_measurement_data_analysis_database
   prd_fdb_architecture_migration
   measurement_data_analysis_database_scope
   sample_database_experiments_plan
   review_mmfdb_implementation
   review_chinet_mmfdb_transparent_backend
   zmq_migration_review_notes

Modelling notes
---------------

.. toctree::
   :maxdepth: 1

   chimol_todo
   chimol_pymol_render_plan
   pmi_compatible_rmf_prd

Process
-------

.. toctree::
   :maxdepth: 1

   ci-act
   VERSIONING
   RELEASES
