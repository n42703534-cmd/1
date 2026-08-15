#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
  library(dplyr)
  library(tidyr)
  library(readr)
  library(scales)
  library(ggrepel)
  library(svglite)
  library(ragg)
  library(grid)
})

root <- normalizePath(".", winslash = "/", mustWork = TRUE)
out_dir <- file.path(root, "outputs", "nature_r_figures_v4")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

low_dir <- file.path(root, "outputs", "algorithm_compare", "mode1_20260623_163319")
high_dir <- file.path(root, "outputs", "algorithm_compare", "mode4_20260623_170538")
abl_dir <- file.path(root, "outputs", "ablation", "mode4_20260609_222716")
sens_dir <- file.path(root, "outputs", "sensitivity", "mode4_20260608_064817")

baseline_key <- "ImprovedAStar"
adaptive_key <- "AdaptiveQueueAwareAStar"

pal <- list(
  ink = "#1F1F1F",
  paper = "#FFFFFF",
  module = "#F1C36D",
  module2 = "#6AB891",
  module3 = "#9FB3BD",
  arrow = "#3F6BAE",
  baseline = "#E7A19B",
  adaptive = "#155A9E",
  adaptive2 = "#3D7DBB",
  risk = "#C43C39",
  warning = "#E8764F",
  safe = "#2D8B57",
  low = "#EAF3F8",
  neutral = "#666666",
  light = "#E6E6E6",
  very_light = "#F7F7F7",
  line16 = "#4C78A8",
  line18 = "#72B7B2",
  line2 = "#F58518",
  line7 = "#54A24B",
  maglev = "#B279A2"
)

theme_set(
  theme_classic(base_size = 7.2, base_family = "Arial") +
    theme(
      axis.line = element_line(linewidth = 0.35, colour = "black"),
      axis.ticks = element_line(linewidth = 0.3, colour = "black"),
      axis.text = element_text(colour = "black"),
      legend.position = "top",
      legend.title = element_blank(),
      legend.key.height = unit(3.6, "mm"),
      legend.key.width = unit(7.5, "mm"),
      legend.text = element_text(size = 6.3),
      plot.title = element_text(size = 8.3, face = "bold", hjust = 0),
      plot.subtitle = element_text(size = 6.6, colour = pal$neutral),
      plot.margin = margin(4, 4, 4, 4),
      panel.grid = element_blank(),
      strip.background = element_blank(),
      strip.text = element_text(size = 7, face = "bold")
    )
)

save_pub <- function(plot, name, width_mm = 183, height_mm = 124, dpi = 600) {
  file_base <- file.path(out_dir, name)
  w <- width_mm / 25.4
  h <- height_mm / 25.4
  svglite::svglite(paste0(file_base, ".svg"), width = w, height = h, bg = "white")
  print(plot)
  dev.off()
  grDevices::cairo_pdf(paste0(file_base, ".pdf"), width = w, height = h, family = "Arial", bg = "white")
  print(plot)
  dev.off()
  ragg::agg_png(paste0(file_base, ".png"), width = w, height = h, units = "in", res = dpi, background = "white")
  print(plot)
  dev.off()
  ragg::agg_tiff(paste0(file_base, ".tiff"), width = w, height = h, units = "in", res = dpi, compression = "lzw", background = "white")
  print(plot)
  dev.off()
}

panel_tag <- function() {
  plot_annotation(tag_levels = "a") &
    theme(plot.tag = element_text(face = "bold", size = 10), plot.tag.position = c(0, 1))
}

read_load <- function(path, load_label) {
  list(
    summary = read_csv(file.path(path, "summary_metrics.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
    line = read_csv(file.path(path, "line_clearance.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
    exits = read_csv(file.path(path, "exit_usage.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
    exit_group = read_csv(file.path(path, "exit_by_source_group.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
    facility = read_csv(file.path(path, "facility_throughput.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
    route = read_csv(file.path(path, "route_chain.csv"), show_col_types = FALSE) %>% mutate(load = load_label)
  )
}

low <- read_load(low_dir, "Low-load")
high <- read_load(high_dir, "High-load")

summary_all <- bind_rows(low$summary, high$summary) %>%
  mutate(method_label = recode(method, !!baseline_key := "Baseline", !!adaptive_key := "Adaptive"))

improvement_metrics <- function(summary_df) {
  summary_df %>%
    select(load, method, T50, T80, T95, T100, queueing_time, congestion_exposure, severe_congestion, peak_density, exit_gini) %>%
    pivot_longer(cols = -c(load, method), names_to = "metric", values_to = "value") %>%
    mutate(value = if_else(metric %in% c("queueing_time", "congestion_exposure", "severe_congestion"), value / 1000, value)) %>%
    pivot_wider(names_from = method, values_from = value) %>%
    mutate(
      reduction_pct = if_else(ImprovedAStar == 0, 0, (ImprovedAStar - AdaptiveQueueAwareAStar) / ImprovedAStar * 100),
      metric_label = recode(
        metric,
        T50 = "T50",
        T80 = "T80",
        T95 = "T95",
        T100 = "Full clearance",
        queueing_time = "Queueing burden",
        congestion_exposure = "Congestion exposure",
        severe_congestion = "Severe exposure",
        peak_density = "Peak density",
        exit_gini = "Exit imbalance"
      )
    )
}

effects <- improvement_metrics(summary_all)
method_cols <- c("Baseline" = pal$baseline, "Adaptive" = pal$adaptive)
signed_cols <- c("lower" = pal$adaptive, "higher" = pal$risk)

# Fig. 1: paper-style technical roadmap --------------------------------------
box_df <- tibble::tribble(
  ~id, ~x, ~y, ~w, ~h, ~label, ~fill,
  "demand", 1.3, 5.3, 1.7, 0.48, "Demand\nLow-load / High-load", pal$module,
  "network", 3.2, 5.3, 1.7, 0.48, "Station facilities\nqueues and exits", pal$module,
  "state", 5.1, 5.3, 1.7, 0.48, "Crowding state\nrisk and density", pal$module,
  "baseline", 1.4, 3.8, 1.8, 0.52, "Baseline\nshortest-path logic", pal$module3,
  "adaptive", 4.0, 3.8, 2.0, 0.52, "Adaptive queue-aware\nroute update", pal$module2,
  "alloc", 6.5, 3.8, 1.9, 0.52, "Passenger allocation\nby line and exit", pal$module,
  "simulate", 2.1, 2.3, 2.0, 0.52, "Evacuation simulation\nfacility throughput", pal$module2,
  "metrics", 4.6, 2.3, 2.0, 0.52, "Performance metrics\nT100, queue, risk", pal$module
)
section_df <- tibble::tribble(
  ~xmin, ~xmax, ~ymin, ~ymax, ~title,
  0.3, 8.9, 4.65, 6.05, "1. Data and state variables",
  0.3, 8.9, 3.05, 4.45, "2. Route optimisation model",
  0.3, 8.9, 1.50, 2.90, "3. Simulation verification and evaluation"
)
arrow_df <- tibble::tribble(
  ~x, ~y, ~xend, ~yend,
  2.15, 5.3, 2.35, 5.3,
  4.05, 5.3, 4.25, 5.3,
  2.3, 3.8, 3.0, 3.8,
  5.05, 3.8, 5.55, 3.8,
  3.1, 2.3, 3.6, 2.3,
  5.6, 2.3, 6.35, 2.3,
  5.1, 5.06, 4.4, 4.12,
  4.0, 3.55, 3.4, 2.56
)

fig1 <- ggplot() +
  geom_rect(data = section_df, aes(xmin = xmin, xmax = xmax, ymin = ymin, ymax = ymax),
            fill = NA, colour = "black", linewidth = 0.35, linetype = "22") +
  geom_text(data = section_df, aes(x = xmin + 0.15, y = ymax - 0.12, label = title),
            hjust = 0, vjust = 1, size = 2.45, fontface = "bold.italic") +
  geom_segment(data = arrow_df, aes(x = x, y = y, xend = xend, yend = yend),
               arrow = arrow(length = unit(2.3, "mm"), type = "closed"),
               linewidth = 0.55, colour = pal$arrow) +
  geom_rect(data = box_df, aes(xmin = x - w/2, xmax = x + w/2, ymin = y - h/2, ymax = y + h/2, fill = fill),
            colour = "black", linewidth = 0.35) +
  geom_text(data = box_df, aes(x = x, y = y, label = label), size = 2.25, lineheight = 0.85, fontface = "bold") +
  scale_fill_identity() +
  annotate("rect", xmin = 6.4, xmax = 8.45, ymin = 4.95, ymax = 5.70, fill = "#5B2A83", colour = NA) +
  annotate("point", x = seq(6.55, 8.25, length.out = 26), y = 5.33 + 0.22 * sin(seq(0, 3*pi, length.out = 26)),
           colour = "#00B7EB", size = 0.55) +
  annotate("point", x = seq(6.65, 8.2, length.out = 16), y = 5.24 + 0.12 * cos(seq(0, 4*pi, length.out = 16)),
           colour = "#FFE600", size = 0.9) +
  annotate("text", x = 7.42, y = 4.82, label = "state snapshot", size = 2.05) +
  annotate("rect", xmin = 6.52, xmax = 8.25, ymin = 1.82, ymax = 2.58, fill = "#F7F7F7", colour = "black", linewidth = 0.3) +
  annotate("segment", x = 6.7, xend = 8.08, y = 2.06, yend = 2.42, colour = pal$adaptive, linewidth = 0.55) +
  annotate("segment", x = 6.7, xend = 8.08, y = 2.46, yend = 2.18, colour = pal$baseline, linewidth = 0.55) +
  annotate("text", x = 7.38, y = 1.70, label = "strategy comparison", size = 2.05) +
  coord_cartesian(xlim = c(0, 9.1), ylim = c(1.35, 6.15), expand = FALSE, clip = "off") +
  labs(title = "Technical roadmap for queue-aware evacuation optimisation") +
  theme_void(base_family = "Arial") +
  theme(plot.title = element_text(size = 8.8, face = "bold", hjust = 0, margin = margin(b = 5)),
        plot.margin = margin(7, 4, 4, 4))
save_pub(fig1, "fig1_technical_roadmap", 183, 108)

# Fig. 2: core effects --------------------------------------------------------
metric_order <- c("Full clearance", "Queueing burden", "Congestion exposure", "Severe exposure", "Peak density", "Exit imbalance")
eff_plot <- effects %>%
  filter(metric_label %in% metric_order) %>%
  mutate(
    metric_label = factor(metric_label, levels = rev(metric_order)),
    load = factor(load, levels = c("Low-load", "High-load")),
    direction = if_else(reduction_pct >= 0, "lower", "higher"),
    label_x = if_else(reduction_pct < 0, reduction_pct / 2, reduction_pct),
    label_h = if_else(reduction_pct < 0, 0.5, -0.08),
    label_col = if_else(reduction_pct < 0, "white", "black")
  )

p2a <- ggplot(eff_plot, aes(reduction_pct, metric_label)) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_col(aes(fill = direction), width = 0.56) +
  geom_text(aes(x = label_x, label = sprintf("%+.1f", reduction_pct), hjust = label_h, colour = label_col), size = 2.15) +
  facet_wrap(~load, nrow = 1) +
  scale_fill_manual(values = signed_cols, guide = "none") +
  scale_colour_identity() +
  scale_x_continuous(limits = c(-18, 49), breaks = c(-15, 0, 20, 40), expand = expansion(mult = c(0.02, 0.08))) +
  labs(title = "Primary effect of adaptive guidance", x = "Reduction relative to baseline (%)", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

quant_df <- summary_all %>%
  filter(load == "High-load") %>%
  select(method_label, T50, T80, T95, T100) %>%
  pivot_longer(-method_label, names_to = "quantile", values_to = "time") %>%
  mutate(quantile = factor(quantile, levels = c("T50", "T80", "T95", "T100")))

p2b <- ggplot(quant_df, aes(quantile, time, group = method_label, colour = method_label, shape = method_label)) +
  geom_line(linewidth = 0.75) +
  geom_point(size = 2.2) +
  scale_colour_manual(values = method_cols) +
  scale_shape_manual(values = c("Baseline" = 17, "Adaptive" = 16)) +
  labs(title = "High-load evacuation quantiles", x = NULL, y = "Time (s)") +
  theme(legend.position = "top")

trade_delta <- summary_all %>%
  filter(method %in% c(baseline_key, adaptive_key)) %>%
  mutate(congestion_k = congestion_exposure / 1000) %>%
  select(load, method_label, T100, congestion_k) %>%
  pivot_wider(names_from = method_label, values_from = c(T100, congestion_k)) %>%
  mutate(delta_time = T100_Adaptive - T100_Baseline, delta_congestion = congestion_k_Adaptive - congestion_k_Baseline)

p2c <- ggplot(trade_delta, aes(delta_time, delta_congestion)) +
  annotate("rect", xmin = 0, xmax = Inf, ymin = -Inf, ymax = 0, fill = pal$low, colour = NA) +
  geom_hline(yintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_segment(aes(x = 0, y = 0, xend = delta_time, yend = delta_congestion),
               arrow = arrow(length = unit(2.1, "mm"), type = "closed"), linewidth = 0.65, colour = pal$adaptive) +
  geom_point(aes(fill = load), shape = 21, size = 3, colour = "black", stroke = 0.35) +
  geom_text_repel(aes(label = sprintf("%s\n%+.0f s, %+.0f", load, delta_time, delta_congestion)),
                  size = 2.1, min.segment.length = 0, segment.size = 0.2) +
  scale_fill_manual(values = c("Low-load" = "white", "High-load" = pal$adaptive), guide = "none") +
  labs(title = "Cost-benefit displacement", x = "Delta clearance time (s)", y = "Delta congestion\n(10^3 passenger-s)") +
  theme(legend.position = "none")

fig2 <- p2a / (p2b | p2c) + plot_layout(heights = c(1, 0.95), widths = c(1, 1)) + panel_tag()
save_pub(fig2, "fig2_core_performance", 183, 130)

# Fig. 3: flow redistribution -------------------------------------------------
line_cols <- c("L16" = pal$line16, "L18" = pal$line18, "L2" = pal$line2, "L7" = pal$line7, "Maglev" = pal$maglev)

top_exits <- high$exit_group %>%
  filter(method_label == adaptive_key) %>%
  mutate(exit_short = gsub("Exit_", "", exit_name)) %>%
  group_by(exit_short) %>%
  summarise(total = sum(people), .groups = "drop") %>%
  slice_max(total, n = 8) %>%
  arrange(desc(total))

source_exit <- high$exit_group %>%
  filter(method_label == adaptive_key) %>%
  mutate(exit_short = gsub("Exit_", "", exit_name)) %>%
  group_by(line, exit_short) %>%
  summarise(people = sum(people), .groups = "drop") %>%
  filter(exit_short %in% top_exits$exit_short, people > 0) %>%
  group_by(line) %>%
  slice_max(people, n = 4, with_ties = FALSE) %>%
  ungroup() %>%
  mutate(
    line = factor(line, levels = c("L16", "L18", "L2", "L7", "Maglev")),
    exit_short = factor(exit_short, levels = rev(top_exits$exit_short))
  )

line_y <- tibble(line = factor(c("L16", "L18", "L2", "L7", "Maglev"), levels = c("L16", "L18", "L2", "L7", "Maglev")),
                 y = seq(4.5, 0.5, length.out = 5))
exit_y <- tibble(exit_short = factor(levels(source_exit$exit_short), levels = levels(source_exit$exit_short)),
                 yend = seq(0.45, 4.55, length.out = length(levels(source_exit$exit_short))))
flow_plot <- source_exit %>%
  left_join(line_y, by = "line") %>%
  left_join(exit_y, by = "exit_short")

p3a <- ggplot() +
  geom_curve(
    data = flow_plot,
    aes(x = 0.18, y = y, xend = 0.82, yend = yend, linewidth = people, colour = line),
    curvature = 0.22, alpha = 0.55, lineend = "round"
  ) +
  geom_point(data = line_y, aes(x = 0.12, y = y, fill = line), shape = 21, size = 4.2, colour = "black", stroke = 0.35) +
  geom_text(data = line_y, aes(x = 0.04, y = y, label = line), hjust = 0, size = 2.45, fontface = "bold") +
  geom_point(data = exit_y, aes(x = 0.88, y = yend), shape = 21, size = 3.4, fill = "white", colour = "black", stroke = 0.35) +
  geom_text(data = exit_y, aes(x = 0.95, y = yend, label = exit_short), hjust = 1, size = 2.1) +
  scale_colour_manual(values = line_cols, guide = "none") +
  scale_fill_manual(values = line_cols, guide = "none") +
  scale_linewidth(range = c(0.35, 4.2), guide = "none") +
  coord_cartesian(xlim = c(0, 1), ylim = c(0, 5), expand = FALSE, clip = "off") +
  labs(title = "Adaptive source-to-exit flow", subtitle = "Line colour encodes source; ribbon width encodes passengers") +
  theme_void(base_family = "Arial") +
  theme(plot.title = element_text(size = 8.3, face = "bold", hjust = 0),
        plot.subtitle = element_text(size = 6.4, colour = pal$neutral))

exit_delta <- high$exits %>%
  mutate(delta_pp = .data[[paste0(adaptive_key, "_pct")]] - .data[[paste0(baseline_key, "_pct")]]) %>%
  slice_max(abs(delta_pp), n = 12) %>%
  arrange(delta_pp) %>%
  mutate(exit_short = gsub("Exit_", "", exit), exit_short = factor(exit_short, levels = exit_short), direction = if_else(delta_pp >= 0, "more", "less"))

p3b <- ggplot(exit_delta, aes(delta_pp, exit_short)) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_col(aes(fill = direction), width = 0.58) +
  scale_fill_manual(values = c("more" = pal$adaptive, "less" = pal$baseline), guide = "none") +
  labs(title = "Exit share redistribution", x = "Adaptive - baseline share (percentage points)", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

line_df <- bind_rows(low$line, high$line) %>%
  select(load, line, all_of(c(baseline_key, adaptive_key))) %>%
  rename(Baseline = all_of(baseline_key), Adaptive = all_of(adaptive_key)) %>%
  mutate(line_load = paste(gsub("-load", "", load), line),
         line_load = factor(line_load, levels = rev(paste(rep(c("Low", "High"), each = 5), rep(c("L16", "L18", "L2", "L7", "Maglev"), 2)))))

p3c <- ggplot(line_df, aes(y = line_load)) +
  geom_segment(aes(x = Baseline, xend = Adaptive, yend = line_load), colour = pal$light, linewidth = 0.7) +
  geom_point(aes(x = Baseline), colour = pal$baseline, shape = 17, size = 2.1) +
  geom_point(aes(x = Adaptive), colour = pal$adaptive, shape = 16, size = 2.1) +
  labs(title = "Line clearance redistribution", x = "Line clearance time (s)", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

fig3 <- p3a / (p3b | p3c) + plot_layout(heights = c(1.12, 0.88), widths = c(1, 1)) + panel_tag()
save_pub(fig3, "fig3_flow_redistribution", 183, 130)

# Fig. 4: facility-level mechanism -------------------------------------------
facility <- high$facility %>%
  mutate(delta = .data[[adaptive_key]] - .data[[baseline_key]],
         total = pmax(.data[[baseline_key]], .data[[adaptive_key]]))

short_node <- function(x) {
  x <- gsub("^VN_", "", x)
  x <- gsub("^Gate_", "G ", x)
  x <- gsub("^Stair_", "St ", x)
  x <- gsub("^Escalator_", "Esc ", x)
  x <- gsub("_Entrance$", " ent", x)
  x <- gsub("_Arrival$", " arr", x)
  x <- gsub("_Corner_", " c", x)
  x <- gsub("_", " ", x)
  ifelse(nchar(x) > 22, paste0(substr(x, 1, 20), "..."), x)
}

shift_fac <- facility %>%
  slice_max(abs(delta), n = 14) %>%
  arrange(delta) %>%
  mutate(facility_short = factor(short_node(facility), levels = short_node(facility)),
         direction = if_else(delta >= 0, "more", "less"))

p4a <- ggplot(shift_fac, aes(delta, facility_short, fill = direction)) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_col(width = 0.6) +
  scale_fill_manual(values = c("more" = pal$adaptive, "less" = pal$baseline), guide = "none") +
  labs(title = "Facility load shifted by adaptive routing", x = "Adaptive - baseline passengers", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

top_fac <- facility %>%
  slice_max(total, n = 10) %>%
  mutate(facility_short = factor(short_node(facility), levels = rev(short_node(facility)))) %>%
  select(facility_short, all_of(c(baseline_key, adaptive_key))) %>%
  pivot_longer(-facility_short, names_to = "method", values_to = "people") %>%
  mutate(method = recode(method, !!baseline_key := "Baseline", !!adaptive_key := "Adaptive"),
         method = factor(method, levels = c("Baseline", "Adaptive")))

p4b <- ggplot(top_fac, aes(method, people, group = facility_short)) +
  geom_line(colour = "#BDBDBD", linewidth = 0.45) +
  geom_point(aes(colour = method), size = 2.35) +
  geom_text_repel(
    data = top_fac %>% filter(method == "Adaptive"),
    aes(label = facility_short),
    size = 1.9, min.segment.length = 0, segment.size = 0.2, nudge_x = 0.08, direction = "y", hjust = 0
  ) +
  scale_colour_manual(values = method_cols, guide = "none") +
  scale_x_discrete(expand = expansion(mult = c(0.08, 0.34))) +
  labs(title = "High-throughput facilities", x = NULL, y = "Passengers") +
  theme(axis.line.x = element_blank(), axis.ticks.x = element_blank())

route_layer <- high$route %>%
  group_by(method, chain_type) %>%
  summarise(people = sum(people), .groups = "drop") %>%
  mutate(method = recode(method, !!baseline_key := "Baseline", !!adaptive_key := "Adaptive"),
         chain_type = recode(chain_type, facility = "Facilities", exit = "Exits"))

p4c <- ggplot(route_layer, aes(chain_type, people / 1000, fill = method)) +
  geom_col(position = position_dodge(width = 0.6), width = 0.52) +
  scale_fill_manual(values = method_cols) +
  labs(title = "Route-chain burden", x = NULL, y = "Passenger appearances (10^3)") +
  theme(legend.position = "none")

fig4 <- p4a | p4b | p4c + plot_layout(widths = c(1.02, 1.05, 0.78)) + panel_tag()
save_pub(fig4, "fig4_facility_mechanism", 183, 92)

# Fig. 5: ablation evidence, no isolated sensitivity panels ------------------
abl <- read_csv(file.path(abl_dir, "ablation_results.csv"), show_col_types = FALSE)
comp <- read_csv(file.path(abl_dir, "component_contributions.csv"), show_col_types = FALSE)
sens_summary <- read_csv(file.path(sens_dir, "sensitivity_summary.csv"), show_col_types = FALSE)

abl_metrics <- c("T100", "queue", "congestion", "severe", "gini")
abl_norm <- abl %>%
  filter(variant %in% c("ImprovedAStar", "Full model", "NoWaitingTime (Density)")) %>%
  select(variant, all_of(abl_metrics)) %>%
  pivot_longer(-variant, names_to = "metric", values_to = "value") %>%
  group_by(metric) %>%
  mutate(value = value / value[variant == "ImprovedAStar"]) %>%
  ungroup() %>%
  mutate(
    variant = recode(variant, ImprovedAStar = "Baseline", `Full model` = "Full adaptive", `NoWaitingTime (Density)` = "No waiting-density"),
    metric = factor(recode(metric, T100 = "T100", queue = "Queue", congestion = "Cong.", severe = "Severe", gini = "Gini"), levels = c("T100", "Queue", "Cong.", "Severe", "Gini")),
    change_pct = (value - 1) * 100
  )

comp_loss <- comp %>%
  transmute(Queue = queue_pct, Congestion = congestion_pct, `Risk area` = r_area_pct, Severe = severe_pct) %>%
  pivot_longer(everything(), names_to = "metric", values_to = "increase") %>%
  arrange(increase) %>%
  mutate(metric = factor(metric, levels = metric),
         label_x = if_else(increase > 80, increase - 2.5, increase + 1.7),
         hjust = if_else(increase > 80, 1, 0),
         label_col = if_else(increase > 80, "white", "black"))

p5a <- ggplot(comp_loss, aes(increase, metric)) +
  geom_col(aes(fill = increase), width = 0.6) +
  geom_text(aes(x = label_x, label = sprintf("+%.1f%%", increase), hjust = hjust, colour = label_col), size = 2.45) +
  scale_fill_gradient(low = "#F5D8A8", high = pal$risk, guide = "none") +
  scale_colour_identity() +
  scale_x_continuous(limits = c(0, 108), breaks = c(0, 50, 100), expand = expansion(mult = c(0, 0.04))) +
  labs(title = "Queue-density term is the main safety control", x = "Increase after removing term (%)", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

abl_matrix <- abl_norm %>%
  filter(variant != "Baseline") %>%
  mutate(variant = factor(variant, levels = c("Full adaptive", "No waiting-density")),
         text_col = if_else(abs(change_pct) > 22, "white", "black"))

p5b <- ggplot(abl_matrix, aes(metric, variant, fill = change_pct)) +
  geom_tile(colour = "white", linewidth = 0.45) +
  geom_text(aes(label = sprintf("%+.0f%%", change_pct), colour = text_col), size = 2.35) +
  scale_colour_identity() +
  scale_fill_gradient2(low = pal$adaptive, mid = "white", high = pal$warning, midpoint = 0,
                       limits = c(-50, 50), oob = scales::squish, name = "Change vs\nbaseline") +
  labs(title = "Ablation matrix", x = NULL, y = NULL) +
  theme(axis.line = element_blank(), axis.ticks = element_blank(), legend.position = "right")

summary_cards <- tibble::tribble(
  ~x, ~y, ~label, ~value, ~fill,
  1, 1, "Full\nadaptive", "Queue -33%\nCong. -28%\nSevere -44%", pal$adaptive,
  2, 1, "No queue-\ndensity", "Queue -7%\nCong. +1%\nSevere +12%", pal$warning,
  3, 1, "Protection\nlost", "Severe +98%\nQueue +39%\nCong. +41%", pal$risk
)
summary_arrows <- tibble::tribble(
  ~x, ~xend, ~y, ~yend,
  1.42, 1.62, 1, 1,
  2.42, 2.62, 1, 1
)

p5c <- ggplot() +
  geom_segment(data = summary_arrows, aes(x = x, xend = xend, y = y, yend = yend),
               arrow = arrow(length = unit(2.2, "mm"), type = "closed"),
               linewidth = 0.55, colour = pal$arrow) +
  geom_rect(data = summary_cards, aes(xmin = x - 0.37, xmax = x + 0.37, ymin = y - 0.28, ymax = y + 0.28, fill = fill),
            colour = "black", linewidth = 0.32) +
  geom_text(data = summary_cards, aes(x = x, y = y + 0.13, label = label), size = 1.95, lineheight = 0.8, fontface = "bold", colour = "white") +
  geom_text(data = summary_cards, aes(x = x, y = y - 0.09, label = value), size = 1.72, lineheight = 0.82, colour = "white") +
  scale_fill_identity() +
  coord_cartesian(xlim = c(0.55, 3.45), ylim = c(0.63, 1.38), expand = FALSE, clip = "off") +
  labs(title = "Interpretation of the ablation result") +
  theme_void(base_family = "Arial") +
  theme(plot.title = element_text(size = 8.3, face = "bold", hjust = 0))

top_sens <- sens_summary %>%
  arrange(desc(J_range)) %>%
  slice_head(n = 4) %>%
  mutate(parameter = recode(parameter,
    gate_queue_weight = "gate queue",
    source_release = "source release",
    gate_overload_factor = "gate overload",
    exit_pressure = "exit pressure"
  ),
  parameter = factor(parameter, levels = rev(parameter)))

p5d <- ggplot(top_sens, aes(J_range, parameter)) +
  geom_col(fill = "#4D4D4D", width = 0.52) +
  geom_text(aes(label = sprintf("%.3f", J_range)), hjust = -0.08, size = 2.25) +
  scale_x_continuous(limits = c(0, max(top_sens$J_range) * 1.18), expand = expansion(mult = c(0, 0.02))) +
  labs(title = "Main tuning levers", x = "Objective-score range", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

fig5 <- (p5a | p5b) / (p5c | p5d) + plot_layout(heights = c(0.92, 0.72), widths = c(0.9, 1.1)) + panel_tag()
save_pub(fig5, "fig5_ablation_evidence", 183, 122)

readme <- c(
  "# R Nature-style figure set v4",
  "",
  "Backend: R only (ggplot2 + patchwork + svglite + ragg).",
  "Scenario labels: mode1 -> Low-load; mode4 -> High-load.",
  "",
  "Design reset after inspecting the supplied paper and additional high-impact evacuation / routing figure examples:",
  "1. fig1_technical_roadmap: paper-style technical roadmap with module boxes, dashed sections, arrows, and embedded state/strategy snapshots.",
  "2. fig2_core_performance: primary performance effects, high-load quantiles, and cost-benefit displacement.",
  "3. fig3_flow_redistribution: adaptive source-to-exit flow diagram, exit share shifts, and line clearance redistribution.",
  "4. fig4_facility_mechanism: facility load shifts, high-throughput facility slope plot, and route-chain burden.",
  "5. fig5_ablation_evidence: queue-density ablation evidence; isolated sensitivity-response panels were removed and replaced by interpretation cards plus a compact tuning-lever summary.",
  ""
)
writeLines(readme, file.path(out_dir, "README.md"))

message("Generated R publication figures in: ", out_dir)
