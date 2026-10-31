# C7: figures, built in R with ggplot2 from the CSV files in results/.
# Every figure is labelled "resampled real rows" (DESIGN.md section 4, C7).
# Run from the repository root:  Rscript figures/make_figures.R
#
# Versions used: R 4.6.1, ggplot2 4.0.3, dplyr 1.2.1, scales 1.4.0.
# Colours are the Okabe-Ito colour-blind-safe set, and every rule also has its own
# plotting shape, so the rules can be told apart without colour.
# Cells where fewer than MIN_STOPS runs stopped are left out of panels that are
# computed only among stopped runs (figures 3 and 4). Figure 1 uses all runs.

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
})

MIN_STOPS <- 50

grid <- read.csv("results/primary_grid.csv", stringsAsFactors = FALSE)
note <- "Resampled real rows from the held-out partition of the Criteo uplift file"
rule_labels <- c(M1 = "M1 fixed z", M2 = "M2 fixed Fisher", M3 = "M3 peeking z",
                 M4 = "M4 group-seq OBF", M5 = "M5 mSPRT", M6 = "M6 Bayesian threshold")
rule_colours <- c(M1 = "#0072B2", M2 = "#56B4E9", M3 = "#E69F00",
                  M4 = "#009E73", M5 = "#CC79A7", M6 = "#000000")
rule_shapes <- c(M1 = 16, M2 = 1, M3 = 17, M4 = 15, M5 = 18, M6 = 4)

scale_rules <- list(
  scale_colour_manual(values = rule_colours, labels = rule_labels),
  scale_shape_manual(values = rule_shapes, labels = rule_labels)
)

theme_study <- theme_minimal(base_size = 11) +
  theme(panel.grid.minor = element_blank(), legend.position = "bottom",
        plot.title.position = "plot")

# Figure 1: false-positive rate in Scenario A by rule and n, with the 0.035-0.065 band.
fig1_df <- grid %>% filter(scenario == "A", outcome == "conversion")
fig1 <- ggplot(fig1_df, aes(x = factor(n_per_arm), y = fired_rate, colour = rule, shape = rule,
                            group = rule)) +
  annotate("rect", xmin = -Inf, xmax = Inf, ymin = 0.035, ymax = 0.065, fill = "grey85", alpha = 0.6) +
  geom_hline(yintercept = 0.05, linetype = 2) +
  geom_errorbar(aes(ymin = fired_ci_lo, ymax = fired_ci_hi), width = 0.12, alpha = 0.6,
                position = position_dodge(width = 0.5)) +
  geom_point(size = 2.2, position = position_dodge(width = 0.5)) +
  scale_rules +
  labs(title = "False-positive rate when there is no effect (Scenario A)",
       subtitle = "Shaded band: 0.035 to 0.065. Bars: 95% Monte Carlo intervals. R = 2,000 per cell.",
       x = "Users per arm (n)", y = "Share of runs that declare a winner", colour = NULL, shape = NULL,
       caption = note) +
  theme_study
ggsave("figures/fig1_false_positive_rate.png", fig1, width = 8, height = 5, dpi = 150)

# Figure 2: power by rule and effect fraction at each n (conversion).
fig2_df <- grid %>% filter(scenario != "A", outcome == "conversion") %>%
  mutate(effect = factor(scenario, levels = c("M0.25", "M0.5", "M1.0")))
fig2 <- ggplot(fig2_df, aes(x = n_per_arm, y = positive_rate, colour = rule, shape = rule)) +
  geom_line() + geom_point(size = 1.8) +
  facet_wrap(~effect, labeller = labeller(effect = c(M0.25 = "Effect = 0.25 x unadjusted H difference",
                                                     M0.5 = "Effect = 0.5 x unadjusted H difference",
                                                     M1.0 = "Effect = unadjusted H difference"))) +
  scale_x_log10(breaks = c(2000, 5000, 10000, 25000, 50000), labels = scales::comma) +
  scale_rules +
  labs(title = "Share of runs that declare the correct winner (power)",
       subtitle = "Conversion outcome. The true effect in each panel is the stated fraction of the unadjusted ITT difference in H.",
       x = "Users per arm (n, log scale)", y = "Power (correct direction)", colour = NULL, shape = NULL,
       caption = note) +
  theme_study
ggsave("figures/fig2_power.png", fig2, width = 9, height = 4.8, dpi = 150)

# Figure 3: time to decision, Scenario M(1.0). Cells with fewer than MIN_STOPS stopped runs are dropped.
fig3_df <- grid %>% filter(scenario == "M1.0", outcome == "conversion", n_stopped >= MIN_STOPS)
fig3 <- ggplot(fig3_df, aes(x = factor(n_per_arm), y = median_users_stopped, colour = rule, shape = rule,
                            group = rule)) +
  geom_line() + geom_point(size = 2) +
  scale_rules +
  scale_y_continuous(labels = scales::comma) +
  labs(title = "Users at the stop, for runs that stopped (Scenario M(1.0))",
       subtitle = paste0("Median total users (both arms) among stopped runs. Points with under ",
                         MIN_STOPS, " stops are left out."),
       x = "Users per arm (n)", y = "Median total users at stop", colour = NULL, shape = NULL,
       caption = note) +
  theme_study
ggsave("figures/fig3_time_to_decision.png", fig3, width = 8, height = 5, dpi = 150)

# Figure 4: bias at stop, Scenario M(1.0), relative to the true effect. Thin cells left out.
fig4_df <- grid %>% filter(scenario == "M1.0", outcome == "conversion", n_stopped >= MIN_STOPS)
fig4 <- ggplot(fig4_df, aes(x = factor(n_per_arm), y = bias_ratio, colour = rule, shape = rule, group = rule)) +
  geom_hline(yintercept = 0, linetype = 2) +
  geom_line() + geom_point(size = 2) +
  scale_rules +
  labs(title = "Bias of the estimated lift at the stop (Scenario M(1.0))",
       subtitle = paste0("(Mean estimate at stop minus true effect) / true effect. Points with under ",
                         MIN_STOPS, " stops are left out."),
       x = "Users per arm (n)", y = "Relative bias", colour = NULL, shape = NULL, caption = note) +
  theme_study
ggsave("figures/fig4_bias_at_stop.png", fig4, width = 8, height = 5, dpi = 150)

cat("Wrote figures to figures/\n")
