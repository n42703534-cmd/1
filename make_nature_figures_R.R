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
})

root <- normalizePath(".", winslash = "/", mustWork = TRUE)
out_dir <- file.path(root, "outputs", "nature_r_figures_v2")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

low_dir <- file.path(root, "outputs", "algorithm_compare", "mode1_20260623_163319")
high_dir <- file.path(root, "outputs", "algorithm_compare", "mode4_20260623_170538")
abl_dir <- file.path(root, "outputs", "ablation", "mode4_20260609_222716")
sens_dir <- file.path(root, "outputs", "sensitivity", "mode4_20260608_064817")

baseline_key <- "ImprovedAStar"
adaptive_key <- "AdaptiveQueueAwareAStar"

pal <- list(
  baseline = "#E9A6A1",
  adaptive = "#0F4D92",
  ablation = "#5D9C93",
  orange = "#D55E00",
  pale_blue = "#DDEAF6",
  pale_orange = "#F7E1D6",
  baseline_dark = "#8F4F54",
  adaptive_light = "#B4C0E4",
  neutral = "#4D4D4D",
  neutral_light = "#D8D8D8",
  gain = "#2E9E44",
  loss = "#B64342",
  wash = "#F7F7F7"
)

theme_set(
  theme_classic(base_size = 7.5, base_family = "Arial") +
    theme(
      axis.line = element_line(linewidth = 0.35, colour = "black"),
      axis.ticks = element_line(linewidth = 0.3, colour = "black"),
      axis.text = element_text(colour = "black"),
      legend.position = "top",
      legend.title = element_blank(),
      legend.key.height = unit(3.5, "mm"),
      legend.key.width = unit(7, "mm"),
      legend.text = element_text(size = 6.5),
      plot.title = element_text(size = 8.5, face = "bold", hjust = 0),
      plot.subtitle = element_text(size = 7, colour = pal$neutral),
      plot.margin = margin(4, 4, 4, 4),
      panel.grid = element_blank(),
      strip.background = element_blank(),
      strip.text = element_text(size = 7, face = "bold")
    )
)

save_pub <- function(plot, name, width_mm = 183, height_mm = 118, dpi = 600) {
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

panel_tag <- function(tag) {
  plot_annotation(tag_levels = "a") &
    theme(plot.tag = element_text(face = "bold", size = 10), plot.tag.position = c(0, 1))
}

read_load <- function(path, load_label) {
  list(
    summary = read_csv(file.path(path, "summary_metrics.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
    improvement = read_csv(file.path(path, "improvement_vs_baseline.csv"), show_col_types = FALSE) %>% mutate(load = load_label),
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
    select(load, method, metric, value) %>%
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
signed_cols <- c("lower" = pal$adaptive, "higher" = pal$loss)

metric_order <- c("Full clearance", "Queueing burden", "Congestion exposure", "Severe exposure", "Peak density", "Exit imbalance")

# Fig. 1 ---------------------------------------------------------------------
hero_df <- effects %>%
  filter(load == "High-load", metric_label %in% c("Full clearance", "Queueing burden", "Congestion exposure", "Severe exposure")) %>%
  mutate(
    metric_label = factor(metric_label, levels = rev(c("Full clearance", "Queueing burden", "Congestion exposure", "Severe exposure"))),
    direction = if_else(reduction_pct >= 0, "lower", "higher"),
    label_x = if_else(reduction_pct < 0, reduction_pct / 2, reduction_pct),
    label_h = if_else(reduction_pct < 0, 0.5, -0.08),
    label_col = if_else(reduction_pct < 0, "white", "black")
  )

p1a <- ggplot(hero_df, aes(reduction_pct, metric_label)) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_col(aes(fill = direction), width = 0.58) +
  geom_text(
    aes(x = label_x, label = sprintf("%+.1f%%", reduction_pct), hjust = label_h, colour = label_col),
    size = 2.45
  ) +
  scale_fill_manual(values = signed_cols, guide = "none") +
  scale_colour_identity() +
  scale_x_continuous(limits = c(-13, 49), breaks = c(-10, 0, 20, 40), expand = expansion(mult = c(0.02, 0.06))) +
  labs(
    title = "High-load primary effects",
    x = "Relative change (%)",
    y = NULL
  ) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

trade_df <- summary_all %>%
  filter(method %in% c(baseline_key, adaptive_key)) %>%
  mutate(
    congestion_k = congestion_exposure / 1000,
    method_label = factor(method_label, levels = c("Baseline", "Adaptive")),
    load = factor(load, levels = c("Low-load", "High-load"))
  )

trade_delta <- trade_df %>%
  select(load, method_label, T100, congestion_k) %>%
  pivot_wider(names_from = method_label, values_from = c(T100, congestion_k)) %>%
  mutate(
    delta_time = T100_Adaptive - T100_Baseline,
    delta_congestion = congestion_k_Adaptive - congestion_k_Baseline,
    label = sprintf("%s\n%+.0f s, %+.0f x10^3", load, delta_time, delta_congestion),
    lab_x = if_else(load == "High-load", delta_time - 2, delta_time + 2),
    lab_y = if_else(load == "High-load", delta_congestion + 52, delta_congestion - 24),
    hjust = if_else(load == "High-load", 1, 0)
  )

p1b <- ggplot(trade_delta, aes(delta_time, delta_congestion)) +
  annotate("rect", xmin = 0, xmax = Inf, ymin = -Inf, ymax = 0, fill = pal$pale_blue, alpha = 0.75) +
  geom_hline(yintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_segment(
    aes(x = 0, y = 0, xend = delta_time, yend = delta_congestion),
    arrow = arrow(length = unit(2.1, "mm"), type = "closed"),
    linewidth = 0.65, colour = pal$adaptive
  ) +
  geom_point(aes(fill = load), shape = 21, size = 3.2, colour = "black", stroke = 0.35) +
  geom_text(aes(x = lab_x, y = lab_y, label = label, hjust = hjust), size = 2.35, lineheight = 0.9) +
  annotate("text", x = 58, y = -575, label = "lower congestion\nwith longer clearance", hjust = 1, vjust = 0, size = 2.25, colour = pal$neutral) +
  scale_fill_manual(values = c("Low-load" = "white", "High-load" = pal$adaptive), guide = "none") +
  scale_x_continuous(limits = c(-4, 70), breaks = c(0, 30, 60), expand = expansion(mult = c(0.02, 0.04))) +
  scale_y_continuous(limits = c(-610, 45), breaks = c(-600, -300, 0), expand = expansion(mult = c(0.02, 0.04))) +
  labs(title = "Strategy-induced displacement", x = "Adaptive - baseline clearance time (s)", y = "Adaptive - baseline\ncongestion exposure (10^3 passenger-s)") +
  theme(legend.position = "none")

card_df <- tibble(
  label = c("Queueing burden", "Congestion exposure", "Severe exposure", "Full clearance"),
  value = c("-33.7%", "-28.4%", "-42.2%", "+7.8%"),
  type = c("gain", "gain", "gain", "cost"),
  x = c(1, 2, 3, 4)
)
p1c <- ggplot(card_df, aes(x, 1)) +
  geom_tile(aes(fill = type), width = 0.92, height = 0.56, colour = "white", linewidth = 0.6) +
  geom_text(aes(label = value), y = 1.08, size = 3.15, fontface = "bold", colour = "white") +
  geom_text(aes(label = label), y = 0.88, size = 2.05, colour = "white") +
  scale_fill_manual(values = c("gain" = pal$adaptive, "cost" = pal$loss), guide = "none") +
  scale_x_continuous(limits = c(0.45, 4.55)) +
  coord_cartesian(clip = "off") +
  labs(title = "High-load summary") +
  theme_void(base_family = "Arial") +
  theme(plot.title = element_text(size = 8.5, face = "bold", hjust = 0))

fig1 <- (p1a | p1b) / p1c +
  plot_layout(heights = c(1, 0.34), widths = c(1.05, 1)) +
  plot_annotation(
    title = "Adaptive guidance trades a small delay for lower crowding risk",
    subtitle = "Values are relative to the baseline strategy; scenario labels are reported as Low-load and High-load.",
    tag_levels = "a"
  ) &
  theme(
    plot.title = element_text(size = 10.5, face = "bold", hjust = 0),
    plot.subtitle = element_text(size = 7.2, colour = pal$neutral),
    plot.tag = element_text(face = "bold", size = 10),
    plot.tag.position = c(0, 1)
  )
save_pub(fig1, "fig1_core_claim", 183, 112)

# Fig. 2 ---------------------------------------------------------------------
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
  geom_col(aes(fill = direction), width = 0.52) +
  geom_text(
    aes(x = label_x, label = sprintf("%+.1f", reduction_pct), hjust = label_h, colour = label_col),
    size = 2.15
  ) +
  facet_wrap(~load, nrow = 1) +
  scale_fill_manual(values = signed_cols, guide = "none") +
  scale_colour_identity() +
  scale_x_continuous(limits = c(-18, 49), breaks = c(-15, 0, 20, 40), expand = expansion(mult = c(0.02, 0.07))) +
  labs(title = "Primary effects across demand levels", x = "Reduction relative to baseline (%)", y = NULL) +
  theme(panel.grid.major.x = element_line(linewidth = 0.25, colour = "#E8E8E8"))

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
  theme(legend.position = "top", panel.grid.major.y = element_line(linewidth = 0.25, colour = "#E8E8E8"))

density_df <- summary_all %>%
  filter(load %in% c("Low-load", "High-load")) %>%
  mutate(method_label = factor(method_label, levels = c("Baseline", "Adaptive")))

p2c <- ggplot(density_df, aes(load, peak_density, fill = method_label)) +
  geom_col(position = position_dodge(width = 0.62), width = 0.56) +
  geom_text(aes(label = sprintf("%.2f", peak_density)), position = position_dodge(width = 0.62), vjust = -0.35, size = 2.05) +
  scale_fill_manual(values = method_cols) +
  labs(title = "Peak density", x = NULL, y = "persons m^-2") +
  theme(legend.position = "none", panel.grid.major.y = element_line(linewidth = 0.25, colour = "#E8E8E8"))

fig2 <- p2a / (p2b | p2c) + plot_layout(heights = c(1, 0.88), widths = c(1.15, 0.85)) + panel_tag("a")
save_pub(fig2, "fig2_primary_effects", 183, 130)

# Fig. 3 ---------------------------------------------------------------------
line_df <- bind_rows(low$line, high$line) %>%
  select(load, line, all_of(c(baseline_key, adaptive_key))) %>%
  rename(Baseline = all_of(baseline_key), Adaptive = all_of(adaptive_key)) %>%
  mutate(line_load = paste(gsub("-load", "", load), line), line_load = factor(line_load, levels = rev(paste(rep(c("Low", "High"), each = 5), rep(c("L16", "L18", "L2", "L7", "Maglev"), 2)))))

p3a <- ggplot(line_df, aes(y = line_load)) +
  geom_segment(aes(x = Baseline, xend = Adaptive, yend = line_load), colour = pal$neutral_light, linewidth = 0.65) +
  geom_point(aes(x = Baseline), colour = pal$baseline, shape = 17, size = 2.2) +
  geom_point(aes(x = Adaptive), colour = pal$adaptive, shape = 16, size = 2.2) +
  labs(title = "Line clearance is redistributed", x = "Line clearance time (s)", y = NULL) +
  theme(panel.grid.major.x = element_line(linewidth = 0.25, colour = "#E8E8E8"))

exit_delta <- high$exits %>%
  mutate(delta_pp = .data[[paste0(adaptive_key, "_pct")]] - .data[[paste0(baseline_key, "_pct")]]) %>%
  slice_max(abs(delta_pp), n = 12) %>%
  arrange(delta_pp) %>%
  mutate(exit_short = gsub("Exit_", "", exit), exit_short = factor(exit_short, levels = exit_short), direction = if_else(delta_pp >= 0, "higher", "lower"))

p3b <- ggplot(exit_delta, aes(delta_pp, exit_short)) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_col(aes(fill = direction), width = 0.58) +
  scale_fill_manual(values = c("higher" = pal$adaptive, "lower" = pal$baseline), guide = "none") +
  labs(title = "Exit shares shift under high load", x = "Adaptive - baseline share (percentage points)", y = NULL) +
  theme(panel.grid.major.x = element_line(linewidth = 0.25, colour = "#E8E8E8"))

top_exits <- high$exit_group %>%
  filter(method_label == adaptive_key) %>%
  mutate(exit_short = gsub("Exit_", "", exit_name)) %>%
  group_by(exit_short) %>%
  summarise(total = sum(people), .groups = "drop") %>%
  slice_max(total, n = 9) %>%
  arrange(desc(total))

source_exit <- high$exit_group %>%
  filter(method_label == adaptive_key) %>%
  mutate(exit_short = gsub("Exit_", "", exit_name)) %>%
  group_by(line, exit_short) %>%
  summarise(people = sum(people), .groups = "drop") %>%
  filter(exit_short %in% top_exits$exit_short) %>%
  mutate(
    exit_short = factor(exit_short, levels = top_exits$exit_short),
    line = factor(line, levels = c("L16", "L18", "L2", "L7", "Maglev"))
  ) %>%
  complete(line, exit_short, fill = list(people = 0))

p3c <- ggplot(source_exit, aes(exit_short, line, fill = people)) +
  geom_tile(colour = "white", linewidth = 0.25) +
  scale_fill_gradient(low = "#F2F0E6", high = pal$adaptive, name = "Passengers") +
  labs(title = "Adaptive source-to-exit allocation", x = NULL, y = NULL) +
  theme(axis.text.x = element_text(angle = 45, hjust = 1), legend.position = "right", panel.background = element_rect(fill = "white", colour = NA))

fig3 <- (p3a | p3b) / p3c + plot_layout(heights = c(1, 1), widths = c(1.05, 1)) + panel_tag("a")
save_pub(fig3, "fig3_flow_redistribution", 183, 128)

# Fig. 4 ---------------------------------------------------------------------
facility <- high$facility %>%
  mutate(delta = .data[[adaptive_key]] - .data[[baseline_key]], total = pmax(.data[[baseline_key]], .data[[adaptive_key]]))

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

top_fac <- facility %>%
  slice_max(total, n = 10) %>%
  mutate(facility_short = factor(short_node(facility), levels = rev(short_node(facility)))) %>%
  select(facility_short, all_of(c(baseline_key, adaptive_key))) %>%
  pivot_longer(-facility_short, names_to = "method", values_to = "people") %>%
  mutate(method = recode(method, !!baseline_key := "Baseline", !!adaptive_key := "Adaptive"))

p4a <- ggplot(top_fac, aes(people, facility_short, fill = method)) +
  geom_col(position = position_dodge(width = 0.62), width = 0.54) +
  scale_fill_manual(values = method_cols) +
  labs(title = "High-throughput bottleneck candidates", x = "Passengers", y = NULL) +
  theme(legend.position = "top", panel.grid.major.x = element_line(linewidth = 0.25, colour = "#E8E8E8"))

shift_fac <- facility %>%
  slice_max(abs(delta), n = 12) %>%
  arrange(delta) %>%
  mutate(facility_short = factor(short_node(facility), levels = short_node(facility)), direction = if_else(delta >= 0, "higher", "lower"))

p4b <- ggplot(shift_fac, aes(delta, facility_short, fill = direction)) +
  geom_vline(xintercept = 0, linewidth = 0.35, colour = pal$neutral) +
  geom_col(width = 0.58) +
  scale_fill_manual(values = c("higher" = pal$adaptive, "lower" = pal$baseline), guide = "none") +
  labs(title = "Largest facility-load shifts", x = "Adaptive - baseline passengers", y = NULL) +
  theme(panel.grid.major.x = element_line(linewidth = 0.25, colour = "#E8E8E8"))

route_layer <- high$route %>%
  group_by(method, chain_type) %>%
  summarise(people = sum(people), .groups = "drop") %>%
  mutate(method = recode(method, !!baseline_key := "Baseline", !!adaptive_key := "Adaptive"), chain_type = recode(chain_type, facility = "Facilities", exit = "Exits"))

p4c <- ggplot(route_layer, aes(chain_type, people / 1000, fill = method)) +
  geom_col(position = position_dodge(width = 0.6), width = 0.52) +
  scale_fill_manual(values = method_cols) +
  labs(title = "Route-chain burden", x = NULL, y = "Passenger appearances (10^3)") +
  theme(legend.position = "none", panel.grid.major.y = element_line(linewidth = 0.25, colour = "#E8E8E8"))

concentration <- bind_rows(
  facility %>% arrange(desc(.data[[baseline_key]])) %>% mutate(rank = row_number(), cum = cumsum(.data[[baseline_key]]) / sum(.data[[baseline_key]]), method = "Baseline"),
  facility %>% arrange(desc(.data[[adaptive_key]])) %>% mutate(rank = row_number(), cum = cumsum(.data[[adaptive_key]]) / sum(.data[[adaptive_key]]), method = "Adaptive")
) %>% filter(rank <= 40)

p4d <- ggplot(concentration, aes(rank, cum, colour = method)) +
  geom_hline(yintercept = 0.5, linetype = "dotted", linewidth = 0.35, colour = pal$neutral) +
  geom_line(linewidth = 0.7) +
  scale_colour_manual(values = method_cols) +
  labs(title = "Facility-load concentration", x = "Top facilities ranked by flow", y = "Cumulative share") +
  theme(legend.position = "bottom")

fig4 <- (p4a | p4b) / (p4c | p4d) + plot_layout(heights = c(1, 0.86), widths = c(1, 1)) + panel_tag("a")
save_pub(fig4, "fig4_bottleneck_mechanism", 183, 125)

# Fig. 5 ---------------------------------------------------------------------
abl <- read_csv(file.path(abl_dir, "ablation_results.csv"), show_col_types = FALSE)
comp <- read_csv(file.path(abl_dir, "component_contributions.csv"), show_col_types = FALSE)
sens_summary <- read_csv(file.path(sens_dir, "sensitivity_summary.csv"), show_col_types = FALSE)
sens_results <- read_csv(file.path(sens_dir, "sensitivity_results.csv"), show_col_types = FALSE)

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
    variant = factor(variant, levels = c("Baseline", "Full adaptive", "No waiting-density")),
    metric = factor(recode(metric, T100 = "T100", queue = "Queue", congestion = "Cong.", severe = "Severe", gini = "Gini"), levels = c("T100", "Queue", "Cong.", "Severe", "Gini"))
  )

abl_change <- abl_norm %>%
  mutate(
    change_pct = (value - 1) * 100,
    variant = factor(variant, levels = c("Baseline", "No waiting-density", "Full adaptive")),
    text_col = if_else(abs(change_pct) > 22, "white", "black")
  ) %>%
  filter(variant != "Baseline")

p5a <- ggplot(abl_change, aes(metric, variant, fill = change_pct)) +
  geom_tile(colour = "white", linewidth = 0.45) +
  geom_text(aes(label = if_else(abs(change_pct) < 0.05, "0", sprintf("%+.0f%%", change_pct)), colour = text_col), size = 2.35) +
  scale_colour_identity() +
  scale_fill_gradient2(
    low = pal$adaptive,
    mid = "white",
    high = pal$orange,
    midpoint = 0,
    limits = c(-50, 50),
    oob = scales::squish,
    name = "Change vs\nbaseline"
  ) +
  labs(title = "Ablation matrix", x = NULL, y = NULL) +
  theme(
    legend.position = "right",
    axis.line = element_blank(),
    axis.ticks = element_blank()
  )

comp_heat <- comp %>%
  transmute(Queue = queue_pct, Congestion = congestion_pct, `Risk area` = r_area_pct, Severe = severe_pct) %>%
  pivot_longer(everything(), names_to = "metric", values_to = "increase") %>%
  mutate(
    metric = factor(metric, levels = metric[order(increase)]),
    label_x = if_else(increase > 80, increase - 2.2, increase + 1.7),
    label_h = if_else(increase > 80, 1, 0),
    label_col = if_else(increase > 80, "white", "black")
  )

p5b <- ggplot(comp_heat, aes(increase, metric)) +
  geom_col(aes(fill = increase), width = 0.58) +
  geom_text(aes(x = label_x, label = sprintf("+%.1f%%", increase), hjust = label_h, colour = label_col), size = 2.45) +
  scale_fill_gradient(low = "#F5D8A8", high = pal$loss, guide = "none") +
  scale_colour_identity() +
  scale_x_continuous(limits = c(0, 108), breaks = c(0, 50, 100), expand = expansion(mult = c(0, 0.04))) +
  labs(title = "Loss after removing queue-density term", x = "Increase relative to full adaptive (%)", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

sens_plot <- sens_summary %>%
  arrange(J_range) %>%
  mutate(parameter_label = factor(recode(parameter,
    gate_queue_weight = "gate queue",
    source_release = "source release",
    gate_overload_factor = "gate overload",
    exit_pressure = "exit pressure",
    downstream_release = "downstream",
    service_rate_weight = "service rate",
    service_wait_time_weight = "service wait",
    density_severe_surcharge = "severe surcharge",
    density_moderate_factor = "moderate factor"
  ), levels = recode(parameter,
    gate_queue_weight = "gate queue",
    source_release = "source release",
    gate_overload_factor = "gate overload",
    exit_pressure = "exit pressure",
    downstream_release = "downstream",
    service_rate_weight = "service rate",
    service_wait_time_weight = "service wait",
    density_severe_surcharge = "severe surcharge",
    density_moderate_factor = "moderate factor"
  )))

p5c <- ggplot(sens_plot, aes(J_range, parameter_label)) +
  geom_segment(aes(x = 0, xend = J_range, yend = parameter_label), linewidth = 0.45, colour = pal$neutral_light) +
  geom_point(aes(fill = J_range), shape = 21, size = 2.7, colour = "black", stroke = 0.28) +
  scale_fill_gradient(low = "#D9D9D9", high = pal$neutral, guide = "none") +
  labs(title = "Parameter sensitivity", x = "Objective-score range", y = NULL) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank())

top_params <- sens_summary %>% arrange(desc(J_range)) %>% slice_head(n = 6) %>% pull(parameter)
param_heat <- sens_results %>%
  filter(parameter %in% top_params) %>%
  select(parameter, level, J) %>%
  bind_rows(sens_summary %>% filter(parameter %in% top_params) %>% transmute(parameter, level = "nominal", J = J_nom)) %>%
  mutate(
    level = factor(level, levels = c("low", "nominal", "high"), labels = c("Low", "Nominal", "High")),
    parameter_label = recode(parameter,
      gate_queue_weight = "gate queue",
      source_release = "source release",
      gate_overload_factor = "gate overload",
      exit_pressure = "exit pressure",
      downstream_release = "downstream",
      service_rate_weight = "service rate"
    ),
    parameter_label = factor(parameter_label, levels = rev(recode(top_params,
      gate_queue_weight = "gate queue",
      source_release = "source release",
      gate_overload_factor = "gate overload",
      exit_pressure = "exit pressure",
      downstream_release = "downstream",
      service_rate_weight = "service rate"
    )))
  )

p5d <- ggplot(param_heat, aes(level, parameter_label, fill = J)) +
  geom_tile(colour = "white", linewidth = 0.35) +
  geom_text(aes(label = sprintf("%.2f", J)), size = 2.25) +
  scale_fill_gradient(low = "#F7FBFF", high = pal$loss, name = "Objective\nscore") +
  labs(title = "Response of top parameters", x = NULL, y = NULL) +
  theme(legend.position = "right", axis.line = element_blank(), axis.ticks = element_blank())

fig5 <- (p5b | p5a) / (p5c | p5d) + plot_layout(widths = c(0.9, 1.1), heights = c(0.9, 1)) + panel_tag("a")
save_pub(fig5, "fig5_ablation_sensitivity", 183, 130)

legend_text <- c(
  "# R Nature-style figure set v2",
  "",
  "Backend: R only (ggplot2 + patchwork + svglite + ragg).",
  "Internal scenario labels:",
  "- mode1_20260623_163319 -> Low-load",
  "- mode4_20260623_170538 -> High-load",
  "",
  "Figure narrative:",
  "1. fig1_core_claim: high-load adaptive guidance reduces crowding burden while increasing full-clearance time; the trade-off is shown as displacement from the baseline.",
  "2. fig2_primary_effects: low- and high-load primary metrics and high-load evacuation quantiles.",
  "3. fig3_flow_redistribution: line, exit, and source-to-exit redistribution.",
  "4. fig4_bottleneck_mechanism: bottleneck and facility-load mechanism.",
  "5. fig5_ablation_sensitivity: queue-density ablation is shown as loss, ablation matrix, and parameter sensitivity.",
  ""
)
writeLines(legend_text, file.path(out_dir, "README.md"))

message("Generated R publication figures in: ", out_dir)
