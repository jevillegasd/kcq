"""Transmon PCell: DiCarlo-style two-island transmon qubit.

Two rectangular islands stacked vertically (the junction/SQUID sits in
the gap between them). Couplers are horizontal CPWs whose center
conductor extends into a notch cut into the left or right edge of an
island, capacitively gapped from the remaining island metal at the
notch's back wall -- not the diagonal radial fingers + T-bar readout of
PDK_Qfoundry's qubits/Transmon.py (used as a reference for the island/
junction-lead geometry below, which is unchanged from it).

Layers (see tech/kcq/waveguides.xml's layer table): metal (positive
trace core) on 1/1, keepout/gap envelopes on 1/0 (kcq's default
technology is negative-lithography: 1/0 is the primary/gap
representation) -- matching kcq.geometry.cpw.CPW's own trace+envelope
pattern: this PCell only ever emits its own metal and its own keepout
envelopes; chip-level ground plane composition (outline minus every
component's keepout) is kcq.geometry.ground's job, not this PCell's.
"""

import math

import pya

from kcq.geometry import pins
from kcq.utils import metadata, xml_parser
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)


class Transmon(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.set_parameters()

    def display_text_impl(self):
        n = len(self.coupler_island) if self.coupler_island else 0
        return f"Transmon(span={self.island_width:.0f}x{self.island_height:.0f}um, {n} couplers)"

    def coerce_parameters_impl(self):
        self.island_width = max(10.0, float(self.island_width))
        self.island_height = max(10.0, float(self.island_height))
        self.island_gap = max(1.0, float(self.island_gap))
        self.corner_radius = max(0.0, float(self.corner_radius))
        self.ground_clearance = max(0.0, float(self.ground_clearance))
        self.keepout_corner_radius = max(0.0, float(self.keepout_corner_radius))
        self.margin = max(0.0, float(self.margin))

        self.arm_width = max(0.0, float(self.arm_width))
        self.arm_gap = max(0.0, float(self.arm_gap))
        self.arm_radius = max(0.0, float(self.arm_radius))
        self.junction_angle = max(0.0, min(90.0, float(self.junction_angle)))
        self.squid_spacing = max(0.0, float(self.squid_spacing))

        n = len(self.coupler_island) if self.coupler_island else 0
        if n == 0:
            return

        normalized_islands = []
        for v in self.coupler_island:
            v = str(v).strip().lower()
            if v not in ("top", "bottom"):
                _LOG.warning("Transmon: invalid coupler_island '%s', defaulting to 'top'", v)
                v = "top"
            normalized_islands.append(v)
        self.coupler_island = normalized_islands

        raw_sides = list(self.coupler_side) if self.coupler_side else []
        normalized_sides = []
        for i in range(n):
            v = raw_sides[i] if i < len(raw_sides) else (raw_sides[-1] if raw_sides else "right")
            v = str(v).strip().lower()
            if v not in ("left", "right"):
                _LOG.warning("Transmon: invalid coupler_side '%s', defaulting to 'right'", v)
                v = "right"
            normalized_sides.append(v)
        self.coupler_side = normalized_sides

    def set_parameters(self):
        # Layers
        self.param("metal_layer", self.TypeLayer, "Metal layer (positive)",
                   default=pya.LayerInfo(1, 1))
        self.param("metal_gap_layer", self.TypeLayer, "Gap/keepout envelope layer",
                   default=pya.LayerInfo(1, 0))
        self.param("devrec_layer", self.TypeLayer, "Device recognition layer",
                   default=pya.LayerInfo(100, 2), hidden=True)
        self.param("ground_exclude_layer", self.TypeLayer, "Ground exclusion layer",
                   default=pya.LayerInfo(1, 5), hidden=True)

        # Islands
        self.param("island_width", self.TypeDouble, "Island width [um]", default=420.0)
        self.param("island_height", self.TypeDouble, "Island height [um]", default=200.0)
        self.param("island_gap", self.TypeDouble,
                   "Vertical gap between islands [um]", default=40.0)
        self.param("corner_radius", self.TypeDouble,
                   "Island corner rounding radius [um]", default=20.0)

        # Junction leads (unchanged from the PDK_Qfoundry reference)
        self.param("add_junction_leads", self.TypeBoolean,
                   "Add leads from the islands toward the future junction position",
                   default=True)
        self.param("junction_pos_x", self.TypeDouble,
                   "X position of the junction center [um]", default=0.0)
        self.param("junction_y_offset", self.TypeDouble,
                   "Vertical offset of the junction from the island-gap center [um]",
                   default=0.0)
        self.param("arm_width", self.TypeDouble, "Junction lead width [um]", default=8.0)
        self.param("arm_gap", self.TypeDouble,
                   "Gap left between a lead tip and the junction position [um]", default=8.0)
        self.param("arm_radius", self.TypeDouble, "Lead corner rounding radius [um]", default=3.0)
        self.param("lead_angled", self.TypeBoolean,
                   "Align leads to the junction fingers (angled Manhattan junction)",
                   default=False)
        self.param("junction_angle", self.TypeDouble,
                   "Junction finger angle [deg, 0-90], used when lead_angled is set",
                   default=0.0)
        self.param("squid_spacing", self.TypeDouble,
                   "SQUID loop: spacing to a second junction lead set, placed at "
                   "junction_pos_x - squid_spacing [um]; 0 disables it", default=0.0)

        # Keepout
        self.param("ground_clearance", self.TypeDouble,
                   "Ground clearance margin around the island bounding box [um]", default=60.0)
        self.param("keepout_corner_radius", self.TypeDouble,
                   "Keepout rectangle corner rounding radius [um]", default=50.0)
        self.param("margin", self.TypeDouble,
                   "Ground exclusion margin beyond the keepout [um]", default=10.0)

        # Couplers: parallel lists, one entry per coupler (matches
        # TransmonStar's coupler_angles/coupler_depths/... convention).
        self.param("coupler_island", self.TypeList,
                   "Coupler target island per coupler: 'top' or 'bottom'",
                   default=["top", "bottom"])
        self.param("coupler_side", self.TypeList,
                   "Coupler entry side per coupler: 'left' or 'right'",
                   default=["right", "left"])
        self.param("coupler_y_offset", self.TypeList,
                   "Y position of each coupler's notch [um]; defaults to its "
                   "island's vertical midpoint if not given", default=[])
        self.param("coupler_wg_width", self.TypeList,
                   "CPW center conductor width per coupler [um]; defaults to the "
                   "active technology's 'resonator' cpw trace_width if empty", default=[])
        self.param("coupler_wg_gap", self.TypeList,
                   "CPW gap per coupler [um]; defaults to the active technology's "
                   "'resonator' cpw gap_width if empty", default=[])
        self.param("coupler_notch_depth", self.TypeList,
                   "Notch depth into the island per coupler [um]", default=[80.0])
        self.param("coupler_notch_gap", self.TypeList,
                   "Capacitive gap at the notch's back wall per coupler [um]", default=[5.0])
        self.param("coupler_extension", self.TypeList,
                   "Waveguide extension beyond the keepout per coupler [um]", default=[30.0])
        self.param("tech_name", self.TypeString,
                   "Technology whose 'resonator' cpw type sizes coupler_wg_width/"
                   "coupler_wg_gap when those are left empty", default="kcq")

        # Rendering
        self.param("resolution", self.TypeInt, "Rounded-corner resolution (points)", default=64)

    def produce_impl(self):
        dbu = self.layout.dbu

        raw_islands = (self._raw_island("top", dbu) + self._raw_island("bottom", dbu)).merged()
        if self.add_junction_leads:
            raw_islands = (raw_islands + self._junction_leads(dbu)).merged()

        coupler_specs = self._coupler_specs()
        conductors = pya.Region()
        keepout_envelopes = pya.Region()
        for spec in coupler_specs:
            envelope = self._coupler_keepout_envelope(spec, dbu)
            raw_islands -= envelope
            conductors += self._coupler_conductor(spec, dbu)
            keepout_envelopes += envelope

        if self.corner_radius > 0.0:
            cr = int(self.corner_radius / dbu)
            island_region = raw_islands.round_corners(cr, cr, self.resolution)
        else:
            island_region = raw_islands

        metal = (island_region + conductors).merged()

        keepout = self._keepout_rect(dbu)
        if self.keepout_corner_radius > 0.0:
            kr = int(self.keepout_corner_radius / dbu)
            keepout = keepout.round_corners(kr, kr, self.resolution)
        keepout = (keepout + keepout_envelopes).merged()

        self.cell.shapes(self.metal_layer).insert(metal)
        self.cell.shapes(self.metal_gap_layer).insert(keepout)

        for index, spec in enumerate(coupler_specs):
            self._add_coupler_pin(index, spec)

        full = (metal + keepout).merged()
        self.cell.shapes(self.devrec_layer).insert(full)
        margin_dbu = int(self.margin / dbu)
        self.cell.shapes(self.ground_exclude_layer).insert(full.sized(margin_dbu))

        metadata.attach_pointer(self.cell, self.layout, "transmon", self._metadata_params())

    # -- couplers ---------------------------------------------------

    def _tech_resonator_params(self):
        return xml_parser.get_cpw_params(self.tech_name, "resonator")

    def _default_island_midpoint_y(self, island):
        g = self.island_gap / 2.0
        return g + self.island_height / 2.0 if island == "top" else -(g + self.island_height / 2.0)

    def _coupler_specs(self):
        n = len(self.coupler_island) if self.coupler_island else 0
        if n == 0:
            return []

        def extend_list(lst, default=None):
            lst = list(lst) if lst else []
            if not lst:
                return [default] * n
            if len(lst) < n:
                lst = lst + [lst[-1]] * (n - len(lst))
            return lst[:n]

        sides = extend_list(self.coupler_side, "right")
        y_offsets_raw = list(self.coupler_y_offset) if self.coupler_y_offset else []
        notch_depths = extend_list(self.coupler_notch_depth, 80.0)
        notch_gaps = extend_list(self.coupler_notch_gap, 5.0)
        extensions = extend_list(self.coupler_extension, 30.0)

        if self.coupler_wg_width:
            wg_widths = extend_list(self.coupler_wg_width)
        else:
            wg_widths = [self._tech_resonator_params()["trace_width"]] * n
        if self.coupler_wg_gap:
            wg_gaps = extend_list(self.coupler_wg_gap)
        else:
            wg_gaps = [self._tech_resonator_params()["gap_width"]] * n

        specs = []
        for i in range(n):
            island = self.coupler_island[i]
            y_offset = y_offsets_raw[i] if i < len(y_offsets_raw) else self._default_island_midpoint_y(island)
            specs.append({
                "island": island,
                "side": sides[i],
                "y_offset": float(y_offset),
                "wg_width": float(wg_widths[i]),
                "wg_gap": float(wg_gaps[i]),
                "notch_depth": float(notch_depths[i]),
                "notch_gap": float(notch_gaps[i]),
                "extension": float(extensions[i]),
            })
        return specs

    def _outward_dir(self, side):
        return 1.0 if side == "right" else -1.0

    def _coupler_x_positions(self, spec):
        outward_dir = self._outward_dir(spec["side"])
        base_x = outward_dir * (self.island_width / 2.0)
        notch_inner_x = base_x - outward_dir * spec["notch_depth"]
        conductor_tip_x = notch_inner_x + outward_dir * spec["notch_gap"]
        keepout_half_width = self.island_width / 2.0 + self.ground_clearance
        conductor_outer_x = outward_dir * (keepout_half_width + spec["extension"])
        return base_x, notch_inner_x, conductor_tip_x, conductor_outer_x

    def _coupler_keepout_envelope(self, spec, dbu):
        _base_x, notch_inner_x, _tip_x, conductor_outer_x = self._coupler_x_positions(spec)
        half_env = spec["wg_width"] / 2.0 + spec["wg_gap"]
        x0, x1 = sorted([conductor_outer_x, notch_inner_x])
        box = pya.DBox(x0, spec["y_offset"] - half_env, x1, spec["y_offset"] + half_env)
        return pya.Region(pya.DPolygon(box).to_itype(dbu))

    def _coupler_conductor(self, spec, dbu):
        _base_x, _notch_inner_x, conductor_tip_x, conductor_outer_x = self._coupler_x_positions(spec)
        x0, x1 = sorted([conductor_outer_x, conductor_tip_x])
        box = pya.DBox(x0, spec["y_offset"] - spec["wg_width"] / 2.0,
                        x1, spec["y_offset"] + spec["wg_width"] / 2.0)
        return pya.Region(pya.DPolygon(box).to_itype(dbu))

    def _add_coupler_pin(self, index, spec):
        _base_x, _notch_inner_x, _tip_x, conductor_outer_x = self._coupler_x_positions(spec)
        angle_deg = 0.0 if spec["side"] == "right" else 180.0
        point = pya.DPoint(conductor_outer_x, spec["y_offset"])
        width = spec["wg_width"] + 2.0 * spec["wg_gap"]
        pins.add_pin(self.cell, self.layout, f"C{index}", point, angle_deg, width,
                     self.metal_layer.layer)

    def _keepout_rect(self, dbu):
        half_w = self.island_width / 2.0 + self.ground_clearance
        half_h = self.island_gap / 2.0 + self.island_height + self.ground_clearance
        box = pya.DBox(-half_w, -half_h, half_w, half_h)
        return pya.Region(pya.DPolygon(box).to_itype(dbu))

    def _metadata_params(self):
        return {
            "island_width": self.island_width, "island_height": self.island_height,
            "island_gap": self.island_gap, "junction_pos_x": self.junction_pos_x,
            "junction_y_offset": self.junction_y_offset, "squid_spacing": self.squid_spacing,
            "coupler_island": list(self.coupler_island) if self.coupler_island else [],
            "coupler_side": list(self.coupler_side) if self.coupler_side else [],
        }

    # -- islands & junction leads (ported from the PDK_Qfoundry reference) --

    def _raw_island(self, which, dbu):
        """Return unrounded top or bottom island."""
        w = self.island_width
        h = self.island_height
        g = self.island_gap / 2.0
        if which == "top":
            box = pya.DBox(-w / 2, g, w / 2, g + h)
        else:
            box = pya.DBox(-w / 2, -g - h, w / 2, -g)
        return pya.Region(pya.DPolygon(box).to_itype(dbu))

    def _junction_leads(self, dbu):
        """Return leads for the junction position, plus a second set offset by
        squid_spacing (to the left) when set, forming a SQUID loop."""
        jx = float(self.junction_pos_x)
        leads = self._junction_lead_pair(jx, dbu)
        squid_spacing = float(self.squid_spacing)
        if squid_spacing > 0.0:
            leads += self._junction_lead_pair(jx - squid_spacing, dbu)
        return leads

    def _junction_lead_pair(self, jx, dbu):
        """Return the (individually rounded) leads reaching from the top/bottom
        islands toward junction position jx, stopping arm_gap short of it."""
        aw = float(self.arm_width)
        ag = float(self.arm_gap)
        ar = float(self.arm_radius)
        jy = float(self.junction_y_offset)
        g = self.island_gap / 2.0
        overlap = ar
        rr = int(ar / dbu)

        leads = pya.Region()
        angled = bool(self.lead_angled) and 30.0 <= float(self.junction_angle) <= 150.0

        if angled:
            theta = float(self.junction_angle)
            half = aw / 2.0
            extra = half - ag
            s0_bot = ag + extra * (theta / 90.0)
            s0_top = ag + extra * (1.0 - theta / 90.0)
            min_len = g

            x_half = self.island_width / 2.0

            # A tilted far edge trails the centerline by (arm_width/2)*|cos(dir)|;
            # pad the penetration by that plus arm_radius so it still clears.
            dir_bot = theta
            pen_bot = ar + half * abs(math.cos(math.radians(dir_bot)))
            s_far_bot = self._lead_far_s(jx, jy, dir_bot, -(g + pen_bot), x_half,
                                          s0_bot + min_len, x_overlap=ar)
            leads += self._angled_lead(jx, jy, dir_bot, s0_bot, s_far_bot, aw, rr, dbu)
            leads += self._island_bridge(jx, jy, dir_bot, s_far_bot, -(g + pen_bot),
                                          x_half, aw, rr, dbu)

            dir_top = theta - 90.0
            pen_top = ar + half * abs(math.cos(math.radians(dir_top)))
            s_far_top = self._lead_far_s(jx, jy, dir_top, g + pen_top, x_half,
                                          s0_top + min_len, x_overlap=ar)
            leads += self._angled_lead(jx, jy, dir_top, s0_top, s_far_top, aw, rr, dbu)
            leads += self._island_bridge(jx, jy, dir_top, s_far_top, g + pen_top,
                                          x_half, aw, rr, dbu)
        else:
            # Leads stay axis-aligned; only their near-edge anchor moves with
            # junction_angle. (arm_gap - arm_width/2)*(sin+cos) never changes
            # sign on [0, 90], so top_tip_y and bot_tip_y can never cross.
            theta_rad = math.radians(float(self.junction_angle))
            cos_t, sin_t = math.cos(theta_rad), math.sin(theta_rad)
            half = aw / 2.0

            bot_cx = jx - ag * sin_t - half * sin_t
            bot_tip_y = jy - ag * cos_t + half * sin_t

            top_cx = jx - ag * cos_t - half * cos_t
            top_tip_y = jy + ag * sin_t - half * cos_t

            bot = pya.DBox(bot_cx - half, -g - overlap, bot_cx + half, bot_tip_y)
            leads += self._rounded_box_region(bot, rr, dbu)

            top = pya.DBox(top_cx - half, top_tip_y, top_cx + half, g + overlap)
            leads += self._rounded_box_region(top, rr, dbu)

        return leads

    def _lead_far_s(self, jx, jy, dir_deg, target_y, x_half, min_len, x_overlap=0.0):
        """Distance (along -dir_deg from the junction position) needed to reach
        target_y, additionally clamped into the island's x-span only when that
        span is actually reachable at positive s (never lets s_far go negative)."""
        rad = math.radians(dir_deg)
        sin_d, cos_d = math.sin(rad), math.cos(rad)
        s_y = (jy - target_y) / sin_d if abs(sin_d) > 1e-9 else 0.0
        s_far = max(s_y, min_len)
        if abs(cos_d) > 1e-9:
            inner = max(0.0, x_half - x_overlap)
            s_a, s_b = (jx - inner) / cos_d, (jx + inner) / cos_d
            s_enter, s_exit = min(s_a, s_b), max(s_a, s_b)
            if s_exit > 0.0:
                s_far = min(max(s_far, s_enter), s_exit)
        return max(s_far, 0.0)

    def _island_bridge(self, cx, cy, dir_deg, s_far, target_y, x_half, width, rr, dbu):
        """Bridge an angled lead's far end into the island whenever it lands
        short in y and/or outside the island's x-span at that y."""
        rad = math.radians(dir_deg)
        far_x = cx - s_far * math.cos(rad)
        far_y = cy - s_far * math.sin(rad)
        inner = max(0.0, x_half - width / 2.0)
        inside_x = min(max(far_x, -inner), inner)
        # Skip drawing anything shorter than the rounding radius: it would
        # be a degenerate sliver once rounded, not a meaningful correction.
        eps = max(rr * dbu, 1e-3)
        if abs(far_y - target_y) < eps and abs(inside_x - far_x) < eps:
            return pya.Region()
        box = pya.DBox(min(far_x, inside_x) - width / 2.0, min(far_y, target_y),
                        max(far_x, inside_x) + width / 2.0, max(far_y, target_y))
        return self._rounded_box_region(box, rr, dbu)

    def _angled_lead(self, cx, cy, dir_deg, s0, s_far, width, rr, dbu):
        """Rectangle spanning [s0, s_far] measured backward (i.e. along
        dir_deg + 180) from the junction position (cx, cy)."""
        box = pya.DBox(s0, -width / 2.0, s_far, width / 2.0)
        poly = pya.DCplxTrans(1.0, dir_deg + 180.0, False, cx, cy) * pya.DPolygon(box)
        return self._rounded_box_region(poly, rr, dbu)

    def _rounded_box_region(self, dshape, rr, dbu):
        """Return dshape (a DBox or DPolygon) as a Region, corners rounded by rr."""
        dpoly = dshape if isinstance(dshape, pya.DPolygon) else pya.DPolygon(dshape)
        ipoly = dpoly.to_itype(dbu)
        if rr > 0:
            ipoly = ipoly.round_corners(rr, rr, 32)
        return pya.Region(ipoly)
