---
title: 'Droplet Wall Interaction Tool: A Python Platform for Droplet Experiments and Qualitative Image Analysis'
tags:
  - Python
  - laboratory automation
  - image analysis
  - droplet experiments
  - scientific software
  - contact angle measurement
authors:
  - name: Kristina Mielke
    orcid: 0009-0009-9946-3315
    corresponding: true
    affiliation: 1
  - name: Arif Rasim Can
    corresponding: false
    affiliation: 1
  - name: Andreas Jupke
    orcide: 0000-0001-6551-5695
    corresponding: false
    affiliation: 1,2

affiliations:
 - name: Fluid Process Engineering (AVT.FVT), RWTH Aachen University, 52074 Aachen, Germany
   index: 1
   ror: https://ror.org/04xfq0f34
 - name: Institute for Bio- and Geosciences (IBG-2), Forschungszentrum Jülich GmbH, 52428 Jülich, Germany
   index: 2

date: 18 February 2026
bibliography: paper.bib
---

# Summary
Droplet hydrodynamics play a central role in many chemical engineering and industrial separation processes, including liquid–liquid extraction, multiphase reactors, and microfluidic applications. In such systems, the motion, deformation, and interaction of droplets with surrounding geometries strongly influence residence times, mass transfer, and overall apparatus performance. Droplets may accelerate, oscillate in shape, or experience significant changes in trajectory depending on whether they rise freely or interact with walls and internal structures such as packings or inserts.
Experimental investigations of these effects require large numbers of high-speed video recordings under varying conditions. As a result, researchers are often confronted with extensive datasets consisting of hundreds of videos that must be evaluated consistently. Manual analysis is time-consuming and limits reproducibility. The Droplet Wall Interaction Tool was developed to address this challenge by providing an automated and extensible platform for droplet motion analysis across different experimental scenarios.
The software enables quantitative characterization of droplet velocity, deformation, equivalent diameter, and contact line behavior. By integrating robust computer vision methods with an interactive graphical interface, the tool supports batch processing of large datasets while maintaining transparency and traceability of the analysis steps.

# Statement of need

Understanding how wall contact and apparatus internals influence droplet motion requires systematic comparison against a well-defined baseline case. In particular, the freely rising droplet without geometric constraints represents an essential reference scenario. Only by quantifying this baseline behavior can researchers determine how droplets are altered by walls, channels, or structured packings. In experimental multiphase flow research, analysis workflows are often based on manual frame-by-frame evaluation or custom scripts developed for individual studies. Such approaches become impractical when datasets scale to hundreds of experiments and make it difficult to ensure consistent parameter selection and reproducible results. The Droplet Wall Interaction Tool was designed to provide a unified workflow for automated droplet characterization across multiple scenarios, including free droplet rise, droplet motion near inclined walls, confinement in channels, and interactions with structured surfaces. The software is intended for researchers in chemical engineering, surface science, multiphase transport, and microfluidics who require reproducible evaluation of droplet dynamics. By enabling automated batch analysis and standardized export formats, the tool supports systematic studies that would otherwise be limited by manual effort.

# State of the Field
A wide range of algorithms and open-source packages exist for droplet contour detection, image segmentation, and contact angle measurement. In particular, tools for sessile droplet analysis on horizontal substrates are commonly used in surface science and wetting research. These approaches are well suited for static and symmetric droplets under controlled laboratory conditions. However, existing tools often become insufficient when droplets are moving, deforming, or interacting with inclined or structured surfaces. Many available contact angle packages rely on symmetry assumptions and are not designed for dynamically evolving droplet shapes. Furthermore, most software solutions focus on isolated tasks such as static contact angle determination and do not provide integrated analysis of droplet velocity, deformation metrics, and contact line dynamics within a single framework. Another key limitation is scalability. While some tools allow automated processing of individual videos, they typically lack support for dataset-level batch evaluation, which is essential in experimental campaigns producing hundreds of recordings. The Droplet Wall Interaction Tool addresses these gaps by combining droplet motion tracking, deformation characterization, and contact line analysis in a unified workflow. Its ability to analyze asymmetric, moving droplets on inclined surfaces represents a distinct scholarly contribution beyond existing alternatives. By integrating baseline free-rise experiments with wall-interaction modes in the same interface, the tool enables systematic comparisons that are difficult to achieve with currently available packages.

# Software design
The Droplet Wall Interaction Tool was developed with the goal of providing an accessible and reproducible workflow for experimental droplet hydrodynamics research. A central design requirement was to combine robust computer vision algorithms with an interface that allows researchers to process large datasets efficiently while maintaining transparency of the underlying analysis.

The software is implemented in Python, ensuring that it can be easily executed, inspected, and adapted by scientists without reliance on proprietary environments. This choice supports extensibility and encourages reuse in related experimental studies.

Droplet detection and contour extraction are based on established methods from the OpenCV ecosystem. In particular, edge-based segmentation using the Canny algorithm provides a reliable foundation for identifying droplet boundaries under varying imaging conditions. Building on these well-tested techniques enables robust droplet recognition across experimental scenarios, including freely rising droplets and droplets interacting with inclined or structured surfaces.

A key contribution of the software is the integration of these algorithms into an interactive graphical user interface (GUI). Many existing droplet analysis workflows rely on scripts that are difficult to scale or reproduce when hundreds of experiments must be evaluated. The GUI was therefore designed not only for usability, but also to enable dataset-level batch processing. Users can define regions of interest, adjust baseline parameters, and immediately verify how selected settings influence droplet detection.

Importantly, the interface provides real-time visual overlays of detected contours and intermediate processing steps. This allows researchers to confirm that droplets are correctly recognized throughout the analysis and reduces the risk of unnoticed parameter misconfiguration.

The image analysis workflow begins with preprocessing steps such as cropping, rotation, and background correction to ensure consistent droplet visibility. Droplet contours are then extracted and geometric features such as area and equivalent diameter are computed. Depending on the experimental mode, baseline intersections are evaluated to determine contact line properties and advancing or receding contact angles. Droplet center positions are tracked over time, enabling velocity calculations from trajectory data. Results are exported in standardized Excel formats, while overlay images are saved to provide qualitative traceability and documentation of the automated evaluation.

# Research impact statement

The Droplet Wall Interaction Tool has already been successfully applied in research on liquid–liquid extraction and droplet–wall interaction phenomena.

Mielke et al. used the software to quantify the influence of stainless-steel wall contact on the velocity of butyl acetate droplets. Their results showed that droplet deformation oscillations occur during free rise and that these oscillations are significantly reduced when droplets interact with a wall surface. [@Mielke.2025]

Potter et al. applied the tool to investigate the invasiveness of film thickness sensors in confined channel experiments. By comparing droplet velocities of different organic phases, including butanol, silicone oil, and butyl acetate, on both stainless-steel and polymer sensor surfaces, they demonstrated that the sensor material does not significantly alter droplet hydrodynamics. This supports the applicability of such sensors for monitoring industrial apparatuses without disturbing flow behavior.[Potter.2026]

These applications demonstrate that the software already contributes to reproducible experimental workflows and provides a foundation for ongoing studies in droplet dynamics and multiphase transport.

# AI usage disclosure
Generative AI tools were used during the development of this project. AI assistance was applied to improve code documentation by adding explanatory comments and to support language refinement of the manuscript, as English is not the native language of the authors.

The authors confirm that all AI-assisted outputs were carefully reviewed, edited, and validated by the human authors. All scientific interpretations, software design decisions, and final text content remain the responsibility of the authors.



