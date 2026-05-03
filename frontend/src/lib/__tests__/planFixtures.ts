import type { RawPlanPreset } from "../plans";

export function makeV2TimingAwareDraftPlan(): RawPlanPreset {
  return {
    schema_version: 2,
    id: "timing-aware-draft",
    name: "Timing Aware Draft",
    version: "2.0",
    created_date: "2026-03-30",
    default_comparison_view_id: "sales_led_operating",
    default_executive_context_view_id: "executive_total_net_new",
    components: {
      sales_led: {
        label: "Sales-Led",
        category: "new_logo_sales_led",
        modeled_status: "scenario_modeled",
        approval_status: "working_draft",
        basis: "consultant_capacity_recut",
        as_of: "2026-03-30",
        arr_targets: {
          canonical_grain: "monthly",
          monthly: {
            "2026-02-01": 750_000,
            "2026-03-01": 825_000,
            "2026-04-01": 925_000,
            "2026-05-01": 1_100_000,
            "2026-06-01": 1_250_000,
            "2026-07-01": 1_450_000,
          },
          quarterly_rollup: {
            Q1FY26: 2_500_000,
            Q2FY26: 3_800_000,
          },
          annual_rollup: 6_300_000,
        },
        seat_targets: {
          canonical_grain: "monthly",
          monthly: {
            "2026-02-01": 9,
            "2026-03-01": 12,
            "2026-04-01": 14,
            "2026-05-01": 18,
            "2026-06-01": 24,
            "2026-07-01": 31,
          },
          quarterly_rollup: {
            Q1FY26: 14,
            Q2FY26: 31,
          },
          annual_rollup: 31,
        },
      },
      plg: {
        label: "PLG",
        category: "self_serve",
        modeled_status: "held_assumption",
        approval_status: "held_from_board_plan",
        basis: "board_hold",
        as_of: "2026-03-30",
        arr_targets: {
          canonical_grain: "quarterly",
          quarterly: {
            Q1FY26: 0,
            Q2FY26: 0,
          },
          annual_rollup: 0,
        },
      },
      expansion: {
        label: "Expansion",
        category: "expansion",
        modeled_status: "held_assumption",
        approval_status: "held_from_board_plan",
        basis: "board_hold",
        as_of: "2026-03-30",
        arr_targets: {
          canonical_grain: "quarterly",
          quarterly: {
            Q1FY26: 0,
            Q2FY26: 0,
          },
          annual_rollup: 0,
        },
      },
    },
    views: {
      sales_led_operating: {
        label: "Sales-Led Plan",
        treatment_class: "operator_comparable",
        supported_grains: ["monthly", "quarterly", "annual"],
        component_ids: ["sales_led"],
        seat_target_owner_component_id: "sales_led",
        derived: true,
      },
      executive_total_net_new: {
        label: "Executive Total Net New",
        treatment_class: "executive_reference",
        context_kind: "total_net_new",
        supported_grains: ["quarterly", "annual"],
        component_ids: ["sales_led", "plg", "expansion"],
        derived: true,
      },
    },
    pacing: {
      Q2FY26: {
        package_provenance: {
          source: "configured_operating_plan",
          derivation: "configured_plan",
          approval_status: "approved",
          freshness_as_of: "2026-03-30",
          freshness_status: "present",
          label: "Approved package",
          notes: [],
        },
        fields: {
          mqls_weekly: {
            value: 113,
          },
          mql_to_s0: {
            value: 0.18,
          },
        },
      },
    },
    forward_context: {
      mode: "note_only",
      promotion_strategy: "requires_new_plan_version",
      effective_after: "2027-01-31",
      reference_series: {
        sales_led_monthly: {
          "2027-02-01": 5_700_000,
        },
        sales_led_ae_targets: {
          "2027-02-01": 56,
        },
      },
      notes: ["Forward context stays note-only until a new plan version is created."],
    },
  };
}

export function makeV2BoardPlan(): RawPlanPreset {
  return {
    schema_version: 2,
    id: "board-plan",
    name: "Board Plan",
    version: "2.0",
    created_date: "2025-12-01",
    default_comparison_view_id: "sales_led_operating",
    components: {
      sales_led: {
        label: "Sales-Led",
        category: "new_logo_sales_led",
        modeled_status: "scenario_modeled",
        approval_status: "approved",
        basis: "board_plan",
        as_of: "2025-12-01",
        arr_targets: {
          canonical_grain: "quarterly",
          quarterly: {
            Q1FY26: 7_000_000,
            Q2FY26: 9_000_000,
          },
          annual_rollup: 16_000_000,
        },
        seat_targets: {
          canonical_grain: "quarterly",
          quarterly_rollup: {
            Q1FY26: 18,
            Q2FY26: 29,
          },
          annual_rollup: 29,
        },
      },
    },
    views: {
      sales_led_operating: {
        label: "Sales-Led Plan",
        treatment_class: "operator_comparable",
        supported_grains: ["quarterly", "annual"],
        component_ids: ["sales_led"],
        seat_target_owner_component_id: "sales_led",
        derived: true,
      },
    },
  };
}
